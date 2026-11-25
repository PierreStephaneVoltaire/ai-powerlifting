package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/http"
	"slices"

	"powerlifting/templates/internal/apperr"
	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/coach"
	"powerlifting/templates/internal/contract"
	"powerlifting/templates/internal/domain"
	"powerlifting/templates/internal/evaluation"
	"powerlifting/templates/internal/execution"
	"powerlifting/templates/internal/library"
)

type Accepted map[string]any

type domainValue interface {
	Value(context.Context, string, string, map[string]any, auth.Caller) (any, error)
}

func (s *Service) evaluate(ctx context.Context, args map[string]any, caller auth.Caller, owners []string, operation *contract.Operation) (any, error) {
	if caller.Nested {
		return nil, apperr.Uncertain("Active domain execution unavailable; do not replay mutations")
	}
	if caller.Person == "" {
		return nil, apperr.Forbidden("Verified acting Person required")
	}
	if caller.ActiveJob() == "" {
		if s.Coach == nil {
			return nil, apperr.Upstream("Coach service unavailable")
		}
		var raw [16]byte
		if _, err := rand.Read(raw[:]); err != nil {
			return nil, err
		}
		queued, err := s.Coach.Submit(ctx, coach.Submission{Operation: "template_evaluate", Arguments: args, Athlete: value(args["pk"]), Person: caller.Person, Key: hex.EncodeToString(raw[:])})
		if err != nil {
			return nil, err
		}
		return Accepted{"job_id": queued.ID, "status": queued.Status}, nil
	}
	if s.Executions == nil || s.Domain == nil {
		return nil, apperr.Upstream("Execution service unavailable")
	}
	sk := value(args["sk"])
	template, err := s.Library.Get(ctx, sk, owners)
	if err != nil {
		return nil, err
	}
	meta, _ := template["meta"].(map[string]any)
	if author := value(meta["author_pk"]); author == "" || !slices.Contains(owners, author) {
		return nil, library.ErrForbidden
	}
	report, err := s.report(ctx, sk, args, caller, owners)
	if err != nil {
		return nil, err
	}
	program, err := s.Sources.ProgramContext(ctx, value(args["pk"]))
	if err != nil {
		return nil, apperr.Upstream("Program service unavailable")
	}
	client, ok := s.Domain.(domainValue)
	if !ok {
		return nil, apperr.Upstream("Goals service unavailable")
	}
	goals, err := client.Value(ctx, "goals", "goals_list", map[string]any{"pk": args["pk"]}, caller)
	if err != nil {
		var status *domain.HTTPError
		if !errors.As(err, &status) || status.Status != http.StatusForbidden {
			return nil, apperr.Upstream("Goals service unavailable")
		}
		goals = nil
	}
	selected := value(args["context"])
	if args["context"] == nil {
		selected = value(meta["program_context"])
	}
	metricValues, _ := report["metrics"].(map[string]any)
	request, err := evaluation.Request(template, program, metricValues, goals, selected)
	if err != nil {
		return nil, err
	}
	executionMeta := execution.Meta{JobID: caller.ActiveJob(), Athlete: value(args["pk"]), Person: caller.Person, Operation: "template_evaluate"}
	outcome, err := s.Executions.Start(ctx, executionMeta, func(ctx context.Context, infer execution.Inferer) (any, error) {
		response, err := infer(ctx, request)
		if err != nil {
			return nil, err
		}
		result, err := evaluation.Parse(response)
		if err != nil {
			return nil, err
		}
		if err = operation.ValidateResult(result); err != nil {
			return nil, apperr.InvalidResult()
		}
		if err = s.Library.SetEvaluation(ctx, sk, owners, result, selected); err != nil {
			return nil, err
		}
		return result, nil
	}, func(context.Context, execution.Meta, any, error) {})
	if err != nil {
		return nil, err
	}
	return outcomeBody(outcome), nil
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

func (s *Service) Resume(ctx context.Context, id string, body map[string]any, caller auth.Caller) (any, error) {
	if s.Executions == nil {
		return nil, apperr.Uncertain("Execution unavailable")
	}
	meta, found := s.Executions.Lookup(id)
	if !found {
		return nil, apperr.Uncertain("Execution unavailable")
	}
	if caller.Person == "" {
		return nil, apperr.Forbidden("Authenticated Person required")
	}
	if _, err := s.Access.Fetch(ctx, "domain_resume", map[string]any{"operation": meta.Operation}, caller); err != nil {
		return nil, err
	}
	if meta.Person != caller.Person || meta.Athlete != caller.Athlete {
		return nil, apperr.Forbidden("Execution belongs to another Person")
	}
	challenge := value(body["challenge_id"])
	outcome, err := s.Executions.Resume(ctx, id, caller.ActiveJob(), caller.Athlete, challenge, body["content"])
	if err != nil {
		return nil, err
	}
	return outcomeBody(outcome), nil
}
