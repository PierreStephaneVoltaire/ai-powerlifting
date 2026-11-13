package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"maps"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/coach"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
	"powerlifting/analytics-ai/internal/reports"
)

type report struct {
	id       string
	identity map[string]any
	store    generation.Store
}

func (s *Service) inputs(operation string, arguments map[string]any) map[string]any {
	inputs := map[string]any{"pk": arguments["pk"]}
	blockKey := func() any {
		if key, _ := arguments["block_key"].(string); key != "" {
			return key
		}
		return "current"
	}
	switch operation {
	case "correlation_analysis":
		inputs["weeks"] = jsonNumber(arguments["weeks"], "4")
		inputs["block"] = blockKey()
		if key, _ := arguments["block"].(string); key != "" {
			inputs["block"] = key
		}
	case "block_correlation_analysis", "block_program_evaluation":
		inputs["block_key"] = blockKey()
	case "multi_block_comparison_analysis":
		keys, _ := arguments["block_keys"].([]any)
		if keys == nil {
			keys = []any{}
		}
		inputs["block_keys"] = keys
	}
	return inputs
}

func (s *Service) identity(ctx context.Context, inputs map[string]any, athlete string, access map[string]any) map[string]any {
	identity := map[string]any{
		"access_requirements": generation.ReadRequirements(access),
		"analysis_version":    cache.AnalysisVersion(ctx, s.KV, athlete),
	}
	block, scoped := inputs["block_key"].(string)
	if !scoped || block == "current" {
		if _, multi := inputs["block_keys"]; !multi {
			identity["date"] = s.Now().UTC().Format("2006-01-02")
		}
	}
	return identity
}

func (s *Service) report(ctx context.Context, operation string, arguments map[string]any, athlete string, access map[string]any) (report, error) {
	inputs := s.inputs(operation, arguments)
	identity := s.identity(ctx, inputs, athlete, access)
	if operation == "correlation_analysis" || operation == "block_correlation_analysis" {
		identity["prompt_version"] = generation.CorrelationPromptVersion
	}
	id, err := generation.Fingerprint(operation, inputs, identity)
	if err != nil {
		return report{}, apperr.Internal(err.Error())
	}
	return report{id: id, identity: identity, store: s.store(athlete)}, nil
}

func missing(id, status string) map[string]any {
	return map[string]any{"cached": false, "cache_miss": true, "generation_id": id, "status": status}
}

func (s *Service) cachedResult(ctx context.Context, r report, record *generation.Record) (any, error) {
	result, err := r.store.Result(ctx, record)
	if errors.Is(err, generation.ErrIncomplete) {
		return nil, apperr.Uncertain(err.Error())
	}
	return result, err
}

func (s *Service) submit(ctx context.Context, call request) (any, error) {
	name := call.operation.Name
	athlete, person := call.caller.Athlete, call.caller.Person
	r, err := s.report(ctx, name, call.arguments, athlete, call.access)
	if err != nil {
		return nil, err
	}
	if truthy(call.arguments["cache_only"]) {
		record, err := r.store.Get(ctx, r.id)
		if err != nil {
			return nil, err
		}
		if record != nil && record.Status == generation.StatusDone {
			return s.cachedResult(ctx, r, record)
		}
		status := "missing"
		if record != nil {
			status = record.Status
		}
		return missing(r.id, status), nil
	}
	record, created, err := r.store.Reserve(ctx, r.id, name, person, truthy(call.arguments["refresh"]), r.identity["access_requirements"].(map[string]any))
	if err != nil {
		return nil, err
	}
	if !created {
		if record.Status == generation.StatusDone {
			return s.cachedResult(ctx, r, record)
		}
		return map[string]any{"generation_id": r.id, "job_id": nullable(record.JobID), "status": record.Status}, nil
	}
	arguments := maps.Clone(call.arguments)
	arguments["refresh"], arguments["cache_only"] = true, false
	arguments["_report_source"] = map[string]any{"access_requirements": r.identity["access_requirements"]}
	job, err := s.Coach.Submit(ctx, coach.Submission{
		Domain: contract.Domain, Operation: name, Arguments: arguments, Athlete: athlete, Person: person,
		Key: fmt.Sprintf("%s:%d", r.id, record.Attempt), GenerationID: r.id, GenerationAttempt: record.Attempt,
	})
	if err != nil {
		status := "uncertain"
		var failure *apperr.Error
		if errors.As(err, &failure) {
			status = "failed"
		}
		_ = r.store.Update(context.WithoutCancel(ctx), r.id, record.Attempt, generation.Item{"status": status, "error": err.Error()})
		return nil, err
	}
	if err := r.store.Update(ctx, r.id, record.Attempt, generation.Item{"job_id": job.ID}); err != nil {
		return nil, err
	}
	return map[string]any{"job_id": job.ID, "status": job.Status, "generation_id": r.id}, nil
}

func nullable(text string) any {
	if text == "" {
		return nil
	}
	return text
}

func (s *Service) handler(operation string) (func(context.Context, reports.Env) (map[string]any, error), bool) {
	switch operation {
	case "correlation_analysis":
		return reports.Correlation, true
	case "block_correlation_analysis":
		return reports.BlockCorrelation, true
	case "program_evaluation":
		return reports.ProgramEvaluation, true
	case "block_program_evaluation":
		return reports.BlockEvaluation, true
	}
	return nil, false
}

func (s *Service) start(ctx context.Context, call request) (Response, error) {
	name := call.operation.Name
	athlete, person := call.caller.Athlete, call.caller.Person
	job := call.caller.ActiveJob()
	generationID, attempt := "", 0
	if call.caller.Generation != nil {
		generationID, attempt = call.caller.Generation.ID, call.caller.Generation.Attempt
	}
	store := s.store(athlete)
	if generationID == "" {
		r, err := s.report(ctx, name, call.arguments, athlete, call.access)
		if err != nil {
			return Response{}, err
		}
		if truthy(call.arguments["cache_only"]) {
			record, err := store.Get(ctx, r.id)
			if err != nil {
				return Response{}, err
			}
			var result any = map[string]any{"cached": false, "cache_miss": true}
			if record != nil && record.Status == generation.StatusDone {
				if result, err = s.cachedResult(ctx, r, record); err != nil {
					return Response{}, err
				}
			}
			return ok(map[string]any{"status": execution.StatusSucceeded, "result": result}), nil
		}
		record, created, err := store.Reserve(ctx, r.id, name, person, truthy(call.arguments["refresh"]), r.identity["access_requirements"].(map[string]any))
		if err != nil {
			return Response{}, err
		}
		if !created {
			var result any = map[string]any{"generation_id": r.id, "status": record.Status}
			if record.Status == generation.StatusDone {
				if result, err = s.cachedResult(ctx, r, record); err != nil {
					return Response{}, err
				}
			}
			return ok(map[string]any{"status": execution.StatusSucceeded, "result": result}), nil
		}
		generationID, attempt = r.id, record.Attempt
		if err := store.Update(ctx, generationID, attempt, generation.Item{"job_id": job}); err != nil {
			return Response{}, err
		}
	}
	meta := execution.Meta{JobID: job, Athlete: athlete, Person: person, Operation: name, GenerationID: generationID, GenerationAttempt: attempt}
	run, finish := s.runner(call, generationID, attempt)
	outcome, err := s.Executions.Start(ctx, meta, run, finish)
	if err != nil {
		return Response{}, err
	}
	return ok(outcomeBody(outcome)), nil
}

func (s *Service) runner(call request, generationID string, attempt int) (execution.Run, execution.Finish) {
	name := call.operation.Name
	athlete := call.caller.Athlete
	store := s.store(athlete)
	var selected []string
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		env := reports.Env{
			Principal: call.principal(), Source: s.Source, Infer: infer, Now: s.Now, Args: call.arguments,
			Saved: s.saved(call),
		}
		var result map[string]any
		var err error
		if name == "multi_block_comparison_analysis" {
			result, selected, err = reports.MultiBlock(ctx, env)
		} else {
			handle, _ := s.handler(name)
			result, err = handle(ctx, env)
		}
		if err != nil {
			return nil, err
		}
		if err := call.operation.ValidateResult(result); err != nil {
			slog.WarnContext(ctx, "invalid result", "operation", name, "error", err.Error())
			return nil, apperr.InvalidResult()
		}
		return result, nil
	}
	finish := func(ctx context.Context, meta execution.Meta, result any, err error) {
		if generationID == "" {
			return
		}
		if err != nil {
			_ = store.Update(ctx, generationID, attempt, generation.Item{"status": "failed", "error": err.Error()})
			return
		}
		if err := store.Complete(ctx, generationID, result, attempt); err != nil {
			_ = store.Update(ctx, generationID, attempt, generation.Item{"status": "failed", "error": err.Error()})
			return
		}
		if name == "multi_block_comparison_analysis" {
			s.saveLifetime(ctx, call, result, selected)
		}
	}
	return run, finish
}

func (s *Service) saved(call request) reports.SavedReport {
	return func(ctx context.Context, operation, blockKey string) map[string]any {
		arguments := map[string]any{"pk": call.caller.Athlete, "block_key": blockKey}
		r, err := s.report(ctx, operation, arguments, call.caller.Athlete, call.access)
		if err != nil {
			return nil
		}
		record, err := r.store.Get(ctx, r.id)
		if err != nil || record == nil || record.Status != generation.StatusDone {
			return nil
		}
		result, err := r.store.Result(ctx, record)
		if object, isObject := result.(map[string]any); err == nil && isObject {
			return object
		}
		return nil
	}
}

func jsonNumber(value any, fallback string) any {
	if value == nil {
		return json.Number(fallback)
	}
	return value
}
