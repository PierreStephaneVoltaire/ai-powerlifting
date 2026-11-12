package reports

import (
	"context"
	"encoding/json"

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

func MultiBlock(ctx context.Context, env Env) (map[string]any, []string, error) {
	var keys []string
	for _, key := range asList(env.Args["block_keys"]) {
		if text, ok := key.(string); ok {
			keys = append(keys, text)
		}
	}
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
	correlations, evaluations, blocks := map[string]any{}, map[string]any{}, []any{}
	for _, key := range selected {
		bundle, err := env.Source.Bundle(ctx, env.Principal, key)
		if err != nil {
			return nil, nil, err
		}
		correlation := savedOrNil(env.Saved(ctx, "block_correlation_analysis", key))
		evaluation := savedOrNil(env.Saved(ctx, "block_program_evaluation", key))
		correlations[key], evaluations[key] = correlation, evaluation
		blocks = append(blocks, map[string]any{
			"block_analysis": bundle, "competitions": rows[key]["competitions"], "goals": rows[key]["goals"],
			"correlation_report": correlation, "program_evaluation_report": evaluation,
		})
	}
	payload := StripMarkers(map[string]any{
		"schema_version": 6, "selected_block_keys": selected, "deterministic": comparison,
		"correlation_reports": correlations, "program_evaluation_reports": evaluations, "blocks": blocks,
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
