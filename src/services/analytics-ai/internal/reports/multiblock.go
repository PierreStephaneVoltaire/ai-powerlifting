package reports

import (
	"context"
	"encoding/json"
	"slices"

	"powerlifting/analytics-ai/internal/prompts"
)

const noPayload = "No block analysis payload was supplied."

var insightLists = []string{
	"similarities", "differences", "what_works", "what_does_not_work", "lift_specific_insights", "multi_block_exercise_roi",
	"cross_block_correlations", "pattern_detections", "volume_dose_response", "bodyweight_relationships", "training_day_frequency",
	"best_value_blocks", "projection_accuracy", "progress_dropoff_points", "fatigue_patterns", "data_limits",
}

var runtimeMarkers = map[string]bool{"cached": true, "cache_miss": true, "cacheStatus": true, "programEvaluationCacheStatus": true, "generated_at": true, "generatedAt": true}

func StripMarkers(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, nested := range typed {
			if !runtimeMarkers[key] {
				out[key] = StripMarkers(nested)
			}
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, nested := range typed {
			out[index] = StripMarkers(nested)
		}
		return out
	}
	return value
}

func insufficientComparison(reason string) map[string]any {
	report := map[string]any{"overall_summary": reason, "insufficient_data": true, "insufficient_data_reason": reason}
	for _, key := range insightLists {
		report[key] = []any{}
	}
	report["data_limits"] = []any{reason}
	return report
}

func ResolveKeys(blocks []map[string]any, requested []string) []string {
	past := map[string]bool{}
	var order []string
	tracked := false
	for _, block := range blocks {
		if current, _ := block["isCurrent"].(bool); current {
			continue
		}
		key := asString(block["blockKey"])
		past[key] = true
		order = append(order, key)
		if _, present := block["stored"]; present {
			tracked = true
		}
	}
	var keys []string
	if len(requested) > 0 {
		for _, key := range requested {
			if past[key] && !slices.Contains(keys, key) {
				keys = append(keys, key)
			}
		}
		return keys
	}
	for _, block := range blocks {
		key := asString(block["blockKey"])
		if !past[key] || (tracked && block["stored"] != true) {
			continue
		}
		keys = append(keys, key)
	}
	return keys
}

func historicalReference(lifetime map[string]any) any {
	if lifetime == nil {
		return nil
	}
	reference := map[string]any{}
	for key, value := range lifetime {
		if key != "blocks" {
			reference[key] = value
		}
	}
	return reference
}

func currentBlockPayload(ctx context.Context, env Env, blocks []map[string]any, key string, bundle map[string]any, comparison map[string]any, correlation, evaluation any) (any, error) {
	entry, found := FindBlock(blocks, key)
	if !found {
		return nil, nil
	}
	snapshot, err := env.Source.Snapshot(ctx, env.Principal)
	if err != nil {
		return nil, err
	}
	sessions := blockSessions(snapshot.Sessions, entry)
	weeks := completedWeeks(sessions)
	return map[string]any{
		"block_key": key, "block_analysis": bundle, "correlation_report": correlation, "program_evaluation_report": evaluation,
		"evaluation_context": evaluationPayload(entry, weeks, sessions, snapshot.Program.AsMap(), bundle, comparison),
	}, nil
}

func MultiBlock(ctx context.Context, env Env) (map[string]any, []string, error) {
	blocks, err := env.Source.Blocks(ctx, env.Principal)
	if err != nil {
		return nil, nil, err
	}
	keys := ResolveKeys(blocks, stringList(env.Args["block_keys"]))
	comparison, err := env.Source.Compare(ctx, env.Principal, keys)
	if err != nil {
		return nil, nil, err
	}
	selected := stringList(comparison["selectedBlockKeys"])
	if len(selected) == 0 {
		return insufficientComparison(noPayload), nil, nil
	}
	rows := map[string]map[string]any{}
	for _, row := range asList(comparison["rows"]) {
		rows[asString(asMap(row)["blockKey"])] = asMap(row)
	}
	var current any
	var historical []any
	var past []string
	for _, key := range selected {
		bundle, err := env.Source.Bundle(ctx, env.Principal, key)
		if err != nil {
			return nil, nil, err
		}
		correlation := savedOrNil(env.Saved(ctx, "block_correlation_analysis", key))
		evaluation := savedOrNil(env.Saved(ctx, "block_program_evaluation", key))
		if entry, found := FindBlock(blocks, key); found && entry.Current {
			if current, err = currentBlockPayload(ctx, env, blocks, key, bundle, comparison, correlation, evaluation); err != nil {
				return nil, nil, err
			}
			continue
		}
		past = append(past, key)
		historical = append(historical, map[string]any{
			"block_key": key, "block_analysis": bundle, "competitions": rows[key]["competitions"], "goals": rows[key]["goals"],
			"correlation_report": correlation, "program_evaluation_report": evaluation,
		})
	}
	var lifetime map[string]any
	if len(past) > 0 {
		if lifetime, err = env.Source.SelectedLifetime(ctx, env.Principal, past); err != nil {
			lifetime = nil
		}
	}
	payload := StripMarkers(map[string]any{
		"schema_version": 7, "task": "Evaluate the current block with the selected past blocks as historical context.",
		"selected_block_keys": selected, "historical_block_keys": past, "current_block": current, "historical_blocks": historical,
		"deterministic": comparison, "lifetime_reference": historicalReference(lifetime),
	})
	user, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return nil, nil, err
	}
	answer, err := ask(ctx, env.Infer, prompts.MultiBlockSystem(), string(user), prompts.Tool("submit_multi_block_comparison"))
	if err != nil {
		return nil, nil, err
	}
	report := map[string]any{"overall_summary": "", "insufficient_data": false, "insufficient_data_reason": ""}
	if summary, ok := answer["overall_summary"].(string); ok {
		report["overall_summary"] = summary
	}
	for _, key := range insightLists {
		if list, ok := answer[key].([]any); ok {
			report[key] = list
		} else {
			report[key] = []any{}
		}
	}
	return report, selected, nil
}

func savedOrNil(report map[string]any) any {
	if report == nil {
		return nil
	}
	return report
}

func stringList(value any) []string {
	var out []string
	for _, item := range asList(value) {
		if text, ok := item.(string); ok {
			out = append(out, text)
		}
	}
	return out
}
