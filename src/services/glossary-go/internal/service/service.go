package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"powerlifting/glossary-go/internal/apperr"
	"powerlifting/glossary-go/internal/athlete"
	"powerlifting/glossary-go/internal/auth"
	"powerlifting/glossary-go/internal/coach"
	"powerlifting/glossary-go/internal/contract"
	"powerlifting/glossary-go/internal/execution"
	"powerlifting/glossary-go/internal/generic"
	"powerlifting/glossary-go/internal/store"
)

type Invalidator interface {
	BumpAnalysis(ctx context.Context, athlete string)
	InvalidateGlossary(ctx context.Context, athlete string)
	InvalidateAllGlossaries(ctx context.Context)
}

type Service struct {
	Registry   *contract.Registry
	Access     auth.AccessClient
	Store      store.Store
	Athletes   athlete.Reader
	Coach      coach.Client
	Executions *execution.Manager
	Generic    *generic.Estimator
	Cache      Invalidator
	Now        func() time.Time

	writes   map[string]handler
	planners map[string]planner
}

type Response struct {
	Status int
	Body   any
}

type call struct {
	operation *contract.Operation
	arguments map[string]any
	caller    auth.Caller
}

func (c call) athlete() string { return c.caller.Athlete }

func (c call) text(key string) string {
	value, _ := c.arguments[key].(string)
	return value
}

type handler func(ctx context.Context, c call) (map[string]any, error)

type plan struct {
	run    execution.Run
	finish func(ctx context.Context, err error)
}

type planner func(ctx context.Context, c call) (plan, error)

func New(s *Service) (*Service, error) {
	s.writes = map[string]handler{
		"exercise_upsert":    s.upsert,
		"exercise_archive":   s.archive(true),
		"exercise_unarchive": s.archive(false),
		"exercise_remove":    s.remove,
		"exercise_set_e1rm":  s.setE1RM,
	}
	s.planners = map[string]planner{
		"glossary_estimate_e1rm":          s.planE1RM,
		"glossary_estimate_fatigue":       s.planFatigue,
		"glossary_estimate_lift_transfer": s.planLiftTransfer,
		"glossary_estimate_muscles":       s.planMuscles,
		"glossary_generate_text":          s.planText,
		generic.Operation:                 s.planGeneric,
	}
	for _, operation := range s.Registry.All() {
		_, deterministic := s.writes[operation.Name]
		_, ai := s.planners[operation.Name]
		if operation.Name != "exercise_get_glossary" && !deterministic && !ai {
			return nil, fmt.Errorf("no handler for %s", operation.Name)
		}
	}
	return s, nil
}

func ok(body any) Response { return Response{Status: http.StatusOK, Body: body} }

func (s *Service) timestamp() string { return s.Now().UTC().Format(time.RFC3339Nano) }

func newID() string {
	raw := make([]byte, 16)
	_, _ = rand.Read(raw)
	return hex.EncodeToString(raw)
}

func (s *Service) Call(ctx context.Context, name string, arguments map[string]any, caller auth.Caller) (Response, error) {
	operation, found := s.Registry.Get(name)
	if !found {
		return Response{}, apperr.UnknownOperation()
	}
	for _, key := range auth.Reserved {
		if _, present := arguments[key]; present {
			return Response{}, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	if err := s.Access.Fetch(ctx, name, arguments, caller); err != nil {
		return Response{}, err
	}
	scoped, err := auth.Scope(operation, arguments, caller)
	if err != nil {
		return Response{}, err
	}
	if err := operation.ValidateInput(scoped); err != nil {
		return Response{}, apperr.Validation(err.Error())
	}
	job := caller.ActiveJob()
	if caller.Nested && job == "" {
		return Response{}, apperr.NestedWithoutExecution()
	}
	current := call{operation: operation, arguments: scoped, caller: caller}
	if operation.Execution == contract.ExecutionAI {
		if caller.Nested {
			return Response{}, apperr.Uncertain("Active domain execution unavailable; do not replay mutations")
		}
		if job != "" {
			return s.start(ctx, current)
		}
		return s.submit(ctx, current)
	}
	result, err := s.deterministic(ctx, current)
	if err != nil {
		return Response{}, err
	}
	if err := operation.ValidateResult(result); err != nil {
		slog.WarnContext(ctx, "invalid result", "operation", name, "error", err.Error())
		return Response{}, apperr.InvalidResult()
	}
	if caller.Nested || job == "" {
		return ok(result), nil
	}
	return ok(map[string]any{"status": execution.StatusSucceeded, "result": result}), nil
}

func (s *Service) deterministic(ctx context.Context, c call) (map[string]any, error) {
	write, writes := s.writes[c.operation.Name]
	if !writes {
		return s.list(ctx, c)
	}
	result, err := write(ctx, c)
	if err != nil {
		return nil, err
	}
	s.touched(ctx, c.athlete())
	return result, nil
}

func (s *Service) touched(ctx context.Context, athlete string) {
	s.Cache.BumpAnalysis(ctx, athlete)
	s.Cache.InvalidateGlossary(ctx, athlete)
}

func (s *Service) submit(ctx context.Context, c call) (Response, error) {
	if c.caller.Person == "" {
		return Response{}, apperr.Forbidden("Verified acting Person required")
	}
	job, err := s.Coach.Submit(ctx, coach.Submission{
		Operation: c.operation.Name, Arguments: c.arguments, Athlete: c.athlete(), Person: c.caller.Person, Key: newID(),
	})
	if err != nil {
		return Response{}, err
	}
	return Response{Status: http.StatusAccepted, Body: map[string]any{"job_id": job.ID, "status": job.Status}}, nil
}

func (s *Service) start(ctx context.Context, c call) (Response, error) {
	prepared, err := s.planners[c.operation.Name](ctx, c)
	if err != nil {
		return Response{}, err
	}
	meta := execution.Meta{JobID: c.caller.ActiveJob(), Athlete: c.athlete(), Person: c.caller.Person, Operation: c.operation.Name}
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		result, err := prepared.run(ctx, infer)
		if err != nil {
			return nil, err
		}
		if err := c.operation.ValidateResult(result); err != nil {
			slog.WarnContext(ctx, "invalid result", "operation", c.operation.Name, "error", err.Error())
			return nil, apperr.InvalidResult()
		}
		return result, nil
	}
	finish := func(ctx context.Context, _ execution.Meta, _ any, err error) {
		if prepared.finish != nil {
			prepared.finish(ctx, err)
		}
	}
	outcome, err := s.Executions.Start(ctx, meta, run, finish)
	if err != nil {
		return Response{}, err
	}
	return ok(outcomeBody(outcome)), nil
}

func outcomeBody(outcome execution.Outcome) map[string]any {
	switch outcome.Status {
	case execution.StatusNeedsInference:
		challenge := outcome.Challenge
		return map[string]any{
			"status": outcome.Status, "execution_id": outcome.ExecutionID, "challenge_id": challenge.ID, "messages": challenge.Messages,
			"tools": challenge.Tools, "response_format": challenge.ResponseFormat, "instruction": challenge.Instruction,
		}
	case execution.StatusRunning:
		return map[string]any{"status": outcome.Status, "execution_id": outcome.ExecutionID}
	}
	return map[string]any{"status": outcome.Status, "result": outcome.Result}
}

func (s *Service) Resume(ctx context.Context, executionID string, body map[string]any, caller auth.Caller) (Response, error) {
	meta, found := s.Executions.Lookup(executionID)
	if !found {
		return Response{}, apperr.Uncertain("Execution unavailable")
	}
	if caller.Person == "" {
		return Response{}, apperr.Forbidden("Authenticated Person required")
	}
	if err := s.Access.Fetch(ctx, "domain_resume", map[string]any{"operation": meta.Operation}, caller); err != nil {
		return Response{}, err
	}
	if meta.Person != caller.Person || meta.Athlete != caller.Athlete {
		return Response{}, apperr.Forbidden("Execution belongs to another Person")
	}
	challengeID, _ := body["challenge_id"].(string)
	outcome, err := s.Executions.Resume(ctx, executionID, caller.ActiveJob(), caller.Athlete, challengeID, body["content"])
	if err != nil {
		return Response{}, err
	}
	return ok(outcomeBody(outcome)), nil
}
