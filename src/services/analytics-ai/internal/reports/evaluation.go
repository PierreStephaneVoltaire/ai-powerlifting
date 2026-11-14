package reports

import (
	"context"
	"encoding/json"

	"google.golang.org/protobuf/types/known/structpb"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/prompts"
)

const insufficientEvaluation = "At least 4 completed weeks are required for a useful full-block evaluation."

var evaluationLists = []string{"what_is_working", "what_is_not_working", "competition_alignment", "goal_status", "competition_strategy", "small_changes", "external_factors", "monitoring_focus"}

func ProgramEvaluation(ctx context.Context, env Env) (map[string]any, error) {
	return evaluate(ctx, env, "current")
}

func BlockEvaluation(ctx context.Context, env Env) (map[string]any, error) {
	return evaluate(ctx, env, env.blockKey())
}

func emptyEvaluation(stance, summary string) map[string]any {
	report := map[string]any{"stance": stance, "summary": summary, "conclusion": "", "weight_class_strategy": map[string]any{"recommendation": "", "recommended_weight_class_kg": nil, "viable_options": []any{}}}
	for _, key := range evaluationLists {
		report[key] = []any{}
	}
	return report
}

func evaluate(ctx context.Context, env Env, blockKey string) (map[string]any, error) {
	blocks, err := env.Source.Blocks(ctx, env.Principal)
	if err != nil {
		return nil, err
	}
	entry, found := FindBlock(blocks, blockKey)
	if !found {
		return nil, apperr.NotFound("Block %s not found", blockKey)
	}
	snapshot, err := env.Source.Snapshot(ctx, env.Principal)
	if err != nil {
		return nil, err
	}
	sessions := blockSessions(snapshot.Sessions, entry)
	weeks := completedWeeks(sessions)
	report := map[string]any{"cached": false, "generated_at": env.timestamp(), "window_start": entry.Start, "weeks": max(1, len(weeks))}
	if !Sufficient(len(weeks)) {
		return InsufficientEvaluation(entry.Start, len(weeks)), nil
	}
	bundle, err := env.Source.Bundle(ctx, env.Principal, blockKey)
	if err != nil {
		return nil, err
	}
	comparison, _ := env.Source.Compare(ctx, env.Principal, []string{blockKey})
	payload := evaluationPayload(entry, weeks, sessions, snapshot.Program.AsMap(), bundle, comparison)
	user, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return nil, err
	}
	answer, err := ask(ctx, env.Infer, prompts.ProgramEvaluationSystem(), string(user), prompts.Tool("report_program_evaluation"))
	if err != nil {
		return nil, err
	}
	report["stance"] = pick(answer, "stance", "monitor")
	report["summary"] = pick(answer, "summary", "")
	for _, key := range evaluationLists {
		report[key] = pick(answer, key, []any{})
	}
	report["weight_class_strategy"] = pick(answer, "weight_class_strategy", map[string]any{"recommendation": "", "recommended_weight_class_kg": nil, "viable_options": []any{}})
	report["conclusion"] = pick(answer, "conclusion", "")
	report["insufficient_data"] = pick(answer, "insufficient_data", false)
	report["insufficient_data_reason"] = pick(answer, "insufficient_data_reason", "")
	return report, nil
}

func blockSessions(raw []*structpb.Struct, entry BlockEntry) []map[string]any {
	var sessions []map[string]any
	for _, item := range raw {
		session := item.AsMap()
		date := asString(session["date"])
		if date >= entry.Start && (entry.End == "" || date <= entry.End) {
			sessions = append(sessions, session)
		}
	}
	return sessions
}

func sessionSummary(session map[string]any) map[string]any {
	summary := map[string]any{"date": session["date"], "week_number": session["week_number"], "completed": Completed(session)}
	for _, key := range []string{"day", "phase", "comments", "session_comments", "body_weight_kg"} {
		if value, present := session[key]; present && value != nil && value != "" {
			summary[key] = value
		}
	}
	var exercises []any
	for _, raw := range asList(session["exercises"]) {
		exercise := asMap(raw)
		line := map[string]any{}
		for _, key := range []string{"name", "sets", "reps", "kg", "rpe", "load_type", "notes"} {
			if value, present := exercise[key]; present && value != nil && value != "" {
				line[key] = value
			}
		}
		if statuses := asList(exercise["set_statuses"]); len(statuses) > 0 {
			line["set_statuses"] = statuses
		}
		exercises = append(exercises, line)
	}
	summary["exercises"] = exercises
	return summary
}

func evaluationPayload(entry BlockEntry, weeks []int, sessions []map[string]any, program, bundle, comparison map[string]any) map[string]any {
	var done, planned []any
	for _, session := range sessions {
		if Completed(session) {
			done = append(done, sessionSummary(session))
		} else {
			planned = append(planned, sessionSummary(session))
		}
	}
	meta := asMap(program["meta"])
	measurements := map[string]any{}
	for _, key := range measurementKeys {
		measurements[key] = meta[key]
	}
	var competitions, goals any
	for _, row := range asList(comparison["rows"]) {
		if asString(asMap(row)["blockKey"]) == entry.Key {
			competitions, goals = asMap(row)["competitions"], asMap(row)["goals"]
		}
	}
	return map[string]any{
		"task": "Evaluate the current powerlifting block and judge how well it is directing the athlete toward the competition goals.",
		"instructions": map[string]any{
			"tone":              "objective sports scientist",
			"stance_preference": "conservative",
			"do_not":            []string{"recommend wholesale redesigns unless a serious issue exists", "overreact to a single metric without context"},
			"focus": []string{
				"overall trajectory", "what is going right", "what is going wrong", "goal alignment for each competition",
				"federation eligibility and weight-class fit for each linked goal", "small useful adjustments only",
				"whether to continue as-is, monitor, or make limited changes",
			},
		},
		"block":                map[string]any{"block_key": entry.Key, "label": entry.Label, "is_current": entry.Current, "start_date": entry.Start, "end_date": entry.End, "week_count": entry.WeekCount, "phases": entry.Raw["phases"], "data_quality_flags": entry.Raw["dataQualityFlags"]},
		"program_meta":         meta,
		"phases":               program["phases"],
		"goals":                goals,
		"full_block_summary":   map[string]any{"analysis_weeks": entry.WeekCount, "completed_sessions": len(done), "completed_weeks": weeks},
		"competitions":         competitions,
		"lift_profiles":        program["lift_profiles"],
		"athlete_measurements": measurements,
		"diet_notes":           program["diet_notes"],
		"completed_sessions":   done,
		"planned_sessions":     planned,
		"weekly_analysis":      bundle["weekly"],
		"historical":           bundle["historical"],
	}
}
