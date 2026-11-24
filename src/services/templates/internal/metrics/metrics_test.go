package metrics

import (
	"testing"
	"time"
)

func TestProgramBuildsPrescriptionWorkloads(t *testing.T) {
	template := map[string]any{"sessions": []any{
		map[string]any{"week_number": 1, "day_of_week": "Saturday", "exercises": []any{map[string]any{"name": "Squat heavy single", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 162.5}, map[string]any{"name": "Bike", "sets": 1, "duration_minutes": 15}}},
		map[string]any{"week_number": 2, "day_of_week": "Saturday", "exercises": []any{map[string]any{"name": "Pause Bench Press", "sets": 2, "reps": 4, "load_type": "percentage", "load_value": 80}}},
	}}
	glossary := []map[string]any{{"id": "g-squat", "name": "Squat", "fatigue_profile": map[string]any{"axial": 0.9, "neural": 0.8, "peripheral": 0.6, "systemic": 0.7}}, {"id": "g-pause", "name": "Pause Bench Press", "category": "bench", "e1rm_estimate": map[string]any{"value_kg": 115}, "primary_muscles": []any{"chest"}}}
	program, summary, err := Program(template, glossary, map[string]any{"squat": 185, "bench": 122.5}, nil, time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	sessions := program["sessions"].([]any)
	if sessions[0].(map[string]any)["date"] != "2026-11-28" || sessions[1].(map[string]any)["date"] != "2026-12-05" {
		t.Fatalf("sessions: %#v", sessions)
	}
	pct := summary["top_set_pct_of_current_max_by_week"].(map[string]any)["1"].(map[string]any)["squat"]
	if pct != 87.8 {
		t.Fatalf("percent = %v", pct)
	}
	exercise := summary["exercises"].(map[string]any)["Pause Bench Press"].(map[string]any)
	if exercise["role"] != "variation" || exercise["lift"] != "bench" {
		t.Fatalf("exercise: %#v", exercise)
	}
	workload := summary["weekly_prescriptions"].(map[string]any)["1"].(map[string]any)
	if workload["cardio_minutes"] != float64(15) || workload["lifting_sets"] != float64(1) {
		t.Fatalf("workload: %#v", workload)
	}
	bench := sessions[1].(map[string]any)["exercises"].([]any)[0].(map[string]any)
	if bench["kg"] != float64(92) {
		t.Fatalf("bench: %#v", bench)
	}
}

func TestCompetitionLiftRejectsVariations(t *testing.T) {
	for input, want := range map[string]string{"Squat heavy single": "squat", "Bench light backoff": "bench", "Deadlift test single": "deadlift", "Pause bench": "", "Snatch deadlift": ""} {
		if got := lift(input); got != want {
			t.Fatalf("%q = %q, want %q", input, got, want)
		}
	}
}

func TestResultFiltersLoggedOnlyAnalysis(t *testing.T) {
	program := map[string]any{"sessions": []any{map[string]any{"week_number": 2, "date": "2026-12-05"}}, "current_maxes": map[string]any{"squat": 185}}
	called := false
	result := Result(program, map[string]any{}, func(args map[string]any) (map[string]any, error) {
		called = true
		if args["week_end"] != 2 || args["ref_date"] != "2026-12-05" || args["block"] != "" {
			t.Fatalf("arguments: %#v", args)
		}
		return map[string]any{"current_maxes": map[string]any{"squat": 185}, "compliance": map[string]any{}, "readiness_score": 1}, nil
	})
	analysis := result["analysis"].(map[string]any)
	if !called || result["weeks"] != 2 || analysis["current_maxes"] == nil || analysis["compliance"] != nil || analysis["readiness_score"] != nil {
		t.Fatalf("result: %#v", result)
	}
	called = false
	result = Result(map[string]any{"sessions": []any{}}, nil, func(map[string]any) (map[string]any, error) { called = true; return nil, nil })
	if called || result["weeks"] != 0 {
		t.Fatalf("empty result: %#v", result)
	}
}
