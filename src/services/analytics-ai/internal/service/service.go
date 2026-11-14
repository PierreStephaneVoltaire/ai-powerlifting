package service

import (
	"context"
	"encoding/json"
	"log/slog"
	"maps"
	"net/http"
	"time"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/coach"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/data"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
)

type Service struct {
	Registry   *contract.Registry
	Access     auth.AccessClient
	Coach      coach.Client
	Source     data.Source
	Exporter   data.Exporter
	KV         cache.KV
	Backend    generation.Backend
	Executions *execution.Manager
	Now        func() time.Time
}

type Response struct {
	Status int
	Body   any
}

func ok(body any) Response { return Response{Status: http.StatusOK, Body: body} }

func (s *Service) store(athlete string) generation.Store {
	return generation.Store{Athlete: athlete, Backend: s.Backend, Now: s.Now}
}

func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case json.Number:
		parsed, err := typed.Float64()
		return err != nil || parsed != 0
	case []any:
		return len(typed) > 0
	}
	return true
}

func (s *Service) Call(ctx context.Context, name string, arguments map[string]any, caller auth.Caller) (Response, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return Response{}, apperr.GenerationWithoutTurn()
	}
	operation, found := s.Registry.Get(name)
	if !found {
		return Response{}, apperr.UnknownOperation()
	}
	for _, key := range auth.Reserved {
		if _, present := arguments[key]; present {
			return Response{}, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	access, err := s.Access.Fetch(ctx, name, arguments, caller)
	if err != nil {
		return Response{}, err
	}
	if operation.InternalOnly && !caller.IsBackend() {
		return Response{}, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(operation, arguments, caller, access)
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
	call := request{operation: operation, arguments: scoped, caller: caller, access: access}
	if operation.Execution == contract.ExecutionAI {
		if caller.Nested {
			return Response{}, apperr.Uncertain("Active domain execution unavailable; do not replay mutations")
		}
		if job != "" {
			return s.start(ctx, call)
		}
		result, err := s.submit(ctx, call)
		return submitted(result), err
	}
	result, err := s.wrapper(ctx, call)
	if err != nil {
		return Response{}, err
	}
	if err := operation.ValidateResult(result); err != nil {
		slog.WarnContext(ctx, "invalid result", "operation", name, "error", err.Error())
		return Response{}, apperr.InvalidResult()
	}
	if caller.Nested || job == "" {
		return submitted(result), nil
	}
	return ok(map[string]any{"status": execution.StatusSucceeded, "result": result}), nil
}

type request struct {
	operation *contract.Operation
	arguments map[string]any
	caller    auth.Caller
	access    auth.Access
}

func (r request) principal() data.Principal {
	return data.Principal{Person: r.caller.Person, Athlete: r.caller.Athlete}
}

func (r request) clone() request {
	r.arguments = maps.Clone(r.arguments)
	return r
}

func submitted(result any) Response {
	if object, isObject := result.(map[string]any); isObject {
		_, hasJob := object["job_id"]
		_, hasGeneration := object["generation_id"]
		if (hasJob || hasGeneration) && object["cached"] != true {
			return Response{Status: http.StatusAccepted, Body: result}
		}
	}
	return ok(result)
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
	if _, err := s.Access.Fetch(ctx, "domain_resume", map[string]any{"operation": meta.Operation}, caller); err != nil {
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

func (s *Service) Regenerate(ctx context.Context, caller auth.Caller, blockKey string) (correlation, evaluation bool) {
	arguments := func() map[string]any {
		return map[string]any{"pk": caller.Athlete, "blockKey": blockKey, "refresh": true}
	}
	_, correlationErr := s.Call(ctx, "analytics.correlation", arguments(), caller)
	_, evaluationErr := s.Call(ctx, "analytics.block_evaluation", arguments(), caller)
	return correlationErr == nil, evaluationErr == nil
}
