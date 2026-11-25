package patch

import (
	"reflect"
	"testing"
)

func TestPatchPreservesInputAndReportsChanges(t *testing.T) {
	template := map[string]any{"sessions": []any{map[string]any{"week_number": 1, "day_of_week": "Monday", "day_index": 1, "exercises": []any{map[string]any{"name": "Squat", "sets": 3, "reps": 5}}}}}
	operations := []any{map[string]any{"op": "replace_exercise", "from": "Squat", "to": "Bench Press"}, map[string]any{"op": "set_prescription", "exercise": "Bench Press", "rep_mode": "amrap"}, map[string]any{"op": "remove_exercise", "exercise": "Deadlift"}}
	patched, changes, unmatched, err := Apply(template, operations, []map[string]any{{"id": "bench", "name": "Bench Press"}})
	if err != nil {
		t.Fatal(err)
	}
	session := patched["sessions"].([]any)[0].(map[string]any)
	ex := session["exercises"].([]any)[0].(map[string]any)
	if ex["name"] != "Bench Press" || ex["glossary_id"] != "bench" || ex["rep_mode"] != "amrap" || ex["reps"] != nil || len(changes) != 2 || len(unmatched) != 1 {
		t.Fatalf("unexpected patch: %#v %#v %#v", ex, changes, unmatched)
	}
	original := template["sessions"].([]any)[0].(map[string]any)["exercises"].([]any)[0].(map[string]any)
	if original["name"] != "Squat" || original["reps"] != 5 {
		t.Fatalf("input changed: %#v", original)
	}
}

func TestWeekdaysAndHash(t *testing.T) {
	input := map[string]any{"sessions": []any{map[string]any{"week_number": 1, "day_of_week": "Monday", "day_index": 1}}}
	operations := []any{map[string]any{"op": "set_session_weekdays", "weekdays": map[string]any{"1": "Friday"}}}
	patched, changes, _, err := Apply(input, operations, nil)
	if err != nil || len(changes) != 1 {
		t.Fatalf("changes %v, error %v", changes, err)
	}
	if got := patched["sessions"].([]any)[0].(map[string]any); !reflect.DeepEqual(got["day_index"], 5) {
		t.Fatalf("unexpected day: %#v", got)
	}
	_, _, _, err = Apply(input, []any{map[string]any{"op": "set_session_weekdays", "weekdays": map[string]any{"2": "Friday"}}}, nil)
	if err == nil {
		t.Fatal("missing out-of-range error")
	}
	hash, err := Hash("template#1", []any{map[string]any{"op": "remove_exercise", "exercise": "Squat"}})
	if err != nil || hash != "098af39930d6c68fc3eaf0718d8d1b2dec48028c1a4d12d2187e447c98623de9" {
		t.Fatalf("hash %q, error %v", hash, err)
	}
}
