package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/auth"
	"powerlifting/liftprofiles/internal/coach"
	"powerlifting/liftprofiles/internal/contract"
	"powerlifting/liftprofiles/internal/execution"
)

type Response struct {
	Status int
	Body   any
}

type Service struct {
	Registry   *contract.Registry
	Access     auth.AccessClient
	Coach      coach.Client
	Executions *execution.Manager
	Handlers   map[string]func(context.Context, map[string]any, execution.Inferer) (any, error)
}

func ok(body any) Response { return Response{Status: http.StatusOK, Body: body} }

func (s *Service) Call(ctx context.Context, name string, args map[string]any, caller auth.Caller) (Response, error) {
	op, found := s.Registry.Get(name)
	if !found {
		return Response{}, apperr.UnknownOperation()
	}
	for _, key := range auth.Reserved {
		if _, present := args[key]; present {
			return Response{}, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	if err := s.Access.Fetch(ctx, name, args, caller); err != nil {
		return Response{}, err
	}
	if op.InternalOnly && !caller.IsBackend() {
		return Response{}, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(op, args, caller)
	if err != nil {
		return Response{}, err
	}
	if err = op.ValidateInput(scoped); err != nil {
		return Response{}, apperr.Validation(err.Error())
	}
	job := caller.ActiveJob()
	if caller.Nested && job == "" {
		return Response{}, apperr.NestedWithoutExecution()
	}
	handler := s.Handlers[name]
	if handler == nil {
		return Response{}, apperr.ExecutionFailed(http.StatusServiceUnavailable, "Operation rewrite is incomplete")
	}
	if op.Execution != contract.ExecutionAI {
		result, err := handler(ctx, scoped, nil)
		if err != nil {
			return Response{}, err
		}
		if err = op.ValidateResult(result); err != nil {
			return Response{}, apperr.InvalidResult()
		}
		if caller.Nested || job == "" {
			return ok(result), nil
		}
		return ok(map[string]any{"status": execution.StatusSucceeded, "result": result}), nil
	}
	if caller.Nested {
		return Response{}, apperr.Uncertain("Active domain execution unavailable; do not replay mutations")
	}
	if job == "" {
		if caller.Person == "" {
			return Response{}, apperr.Forbidden("Verified acting Person required")
		}
		id := make([]byte, 16)
		if _, err = rand.Read(id); err != nil {
			return Response{}, err
		}
		queued, err := s.Coach.Submit(ctx, coach.Submission{Operation: name, Arguments: scoped, Athlete: caller.Athlete, Person: caller.Person, Key: hex.EncodeToString(id)})
		if err != nil {
			return Response{}, err
		}
		return Response{Status: http.StatusAccepted, Body: map[string]any{"job_id": queued.ID, "status": queued.Status}}, nil
	}
	meta := execution.Meta{JobID: job, Athlete: caller.Athlete, Person: caller.Person, Operation: name}
	outcome, err := s.Executions.Start(ctx, meta, func(ctx context.Context, infer execution.Inferer) (any, error) {
		result, err := handler(ctx, scoped, infer)
		if err != nil {
			return nil, err
		}
		if err = op.ValidateResult(result); err != nil {
			return nil, apperr.InvalidResult()
		}
		return result, nil
	}, func(context.Context, execution.Meta, any, error) {})
	if err != nil {
		return Response{}, err
	}
	return ok(outcomeBody(outcome)), nil
}

func outcomeBody(outcome execution.Outcome) map[string]any {
	if outcome.Status == execution.StatusNeedsInference {
		c := outcome.Challenge
		return map[string]any{"status": outcome.Status, "execution_id": outcome.ExecutionID, "challenge_id": c.ID, "messages": c.Messages, "tools": c.Tools, "response_format": c.ResponseFormat, "instruction": c.Instruction}
	}
	if outcome.Status == execution.StatusRunning {
		return map[string]any{"status": outcome.Status, "execution_id": outcome.ExecutionID}
	}
	return map[string]any{"status": outcome.Status, "result": outcome.Result}
}

func (s *Service) Resume(ctx context.Context, id string, body map[string]any, caller auth.Caller) (Response, error) {
	meta, found := s.Executions.Lookup(id)
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
	challenge, _ := body["challenge_id"].(string)
	outcome, err := s.Executions.Resume(ctx, id, caller.ActiveJob(), caller.Athlete, challenge, body["content"])
	if err != nil {
		return Response{}, err
	}
	return ok(outcomeBody(outcome)), nil
}
