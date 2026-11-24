package apply

import (
	"encoding/json"
	"reflect"
	"testing"
	"time"
)

func TestConcretizeHandlesJSONNumbers(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"week_number": json.Number("2"), "day_index": json.Number("2"), "exercises": []any{map[string]any{"name": "Squat", "glossary_id": "squat", "sets": json.Number("3"), "reps": json.Number("5"), "load_type": "percentage", "load_value": json.Number("0.75")}}}}}
	maxes := map[string]any{"squat": json.Number("200")}
	if missing := Missing(template, maxes, nil); len(missing) != 0 {
		t.Fatalf("missing %#v", missing)
	}
	sessions, err := Concretize(template, maxes, nil, time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC), "Monday")
	if err != nil {
		t.Fatal(err)
	}
	if sessions[0]["date"] != "2026-12-01" || sessions[0]["planned_exercises"].([]map[string]any)[0]["kg"] != 150.0 {
		t.Fatalf("sessions %#v", sessions)
	}
}

func TestConcretizeAndMissingMaxes(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"week_number": 1, "day_of_week": "Tuesday", "exercises": []any{map[string]any{"name": "Squat", "glossary_id": "squat", "sets": 3, "reps": 5, "load_type": "percentage", "load_value": 0.8}}}}}
	if got := Missing(template, nil, nil); !reflect.DeepEqual(got, []string{"squat"}) {
		t.Fatalf("missing = %#v", got)
	}
	maxes := map[string]any{"squat": 200.0}
	if got := Missing(template, maxes, nil); len(got) != 0 {
		t.Fatalf("missing = %#v", got)
	}
	sessions, err := Concretize(template, maxes, nil, time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC), "Monday")
	if err != nil {
		t.Fatal(err)
	}
	if len(sessions) != 1 || sessions[0]["date"] != "2026-11-24" {
		t.Fatalf("sessions = %#v", sessions)
	}
	ex := sessions[0]["planned_exercises"].([]map[string]any)[0]
	if ex["kg"] != 160.0 {
		t.Fatalf("exercise = %#v", ex)
	}
}
func TestConcretizeTimedRPEAndRoundEven(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"day_of_week": "Monday", "exercises": []any{map[string]any{"name": "Bike", "sets": 1, "reps": 90, "rep_unit": "seconds", "load_type": "rpe", "load_value": 7}}}}}
	sessions, err := Concretize(template, nil, nil, time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC), "Monday")
	if err != nil {
		t.Fatal(err)
	}
	ex := sessions[0]["planned_exercises"].([]map[string]any)[0]
	if ex["kg"] != nil || ex["rpe_target"] != float64(7) || ex["rep_unit"] != "seconds" {
		t.Fatalf("exercise = %#v", ex)
	}
}

func TestMissingRejectsEmptyExerciseEstimate(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"exercises": []any{map[string]any{"glossary_id": "row", "load_type": "percentage"}}}}}
	glossary := []map[string]any{{"id": "row", "e1rm_estimate": map[string]any{}}}
	if got := Missing(template, nil, glossary); !reflect.DeepEqual(got, []string{"row"}) {
		t.Fatalf("missing = %#v", got)
	}
	glossary[0]["e1rm_estimate"] = map[string]any{"value_kg": 100}
	if got := Missing(template, nil, glossary); len(got) != 0 {
		t.Fatalf("missing = %#v", got)
	}
}

func TestConcretizeRespectsExplicitZeroMax(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"day_of_week": "Monday", "exercises": []any{map[string]any{"name": "Squat", "glossary_id": "squat", "sets": 3, "reps": 5, "load_type": "rpe", "load_value": 8}}}}}
	glossary := []map[string]any{{"id": "squat", "e1rm_estimate": map[string]any{"value_kg": 200}}}
	start := time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC)
	for _, tc := range []struct {
		name     string
		maxes    map[string]any
		wantLoad bool
	}{{"explicit zero", map[string]any{"squat": 0}, false}, {"no max", nil, true}} {
		t.Run(tc.name, func(t *testing.T) {
			sessions, err := Concretize(template, tc.maxes, glossary, start, "Monday")
			if err != nil {
				t.Fatal(err)
			}
			exercise := sessions[0]["planned_exercises"].([]map[string]any)[0]
			if (exercise["kg"] != nil) != tc.wantLoad {
				t.Fatalf("exercise = %#v", exercise)
			}
		})
	}
}
