package payload

import (
	"reflect"
	"testing"
)

func TestPrepareCreatesIndependentNormalizedTemplate(t *testing.T) {
	original := map[string]any{"sessions": []any{
		map[string]any{"week_number": 2, "day_of_week": "Thursday", "exercises": []any{
			map[string]any{"name": "Squat", "glossary_id": "g2", "load_type": "PERCENTAGE", "load_value": 80},
			map[string]any{"name": "Missing", "load_type": "invalid"},
		}},
		map[string]any{"week_number": 2, "day_index": 2, "exercises": []any{map[string]any{"glossary_id": "g1", "load_type": "rpe"}}},
	}}
	got, err := Prepare(original, true)
	if err != nil {
		t.Fatal(err)
	}
	meta := got["meta"].(map[string]any)
	if meta["estimated_weeks"] != 2 || meta["days_per_week"] != 2 || meta["name"] != "Imported Template" {
		t.Fatalf("unexpected metadata: %#v", meta)
	}
	sessions := got["sessions"].([]any)
	first := sessions[0].(map[string]any)
	if first["day_index"] != 4 || first["label"] != "W2D4" || len(first["id"].(string)) != 36 {
		t.Fatalf("unexpected session: %#v", first)
	}
	exercise := first["exercises"].([]any)[0].(map[string]any)
	if exercise["load_value"] != 0.8 || exercise["load_type"] != "percentage" {
		t.Fatalf("unexpected prescription: %#v", exercise)
	}
	if !reflect.DeepEqual(got["required_maxes"], []string{"g2"}) {
		t.Fatalf("unexpected maxes: %#v", got["required_maxes"])
	}
	resolution := got["glossary_resolution"].(map[string]any)
	if resolution["resolution_status"] != "partial" || !reflect.DeepEqual(resolution["unresolved"], []string{"Missing"}) {
		t.Fatalf("unexpected resolution: %#v", resolution)
	}
	if _, ok := original["meta"]; ok {
		t.Fatal("input mutated")
	}
}

func TestPrepareUpdateDoesNotInventMetadata(t *testing.T) {
	got, err := Prepare(map[string]any{"sessions": []any{map[string]any{"day_index": 12, "exercises": []any{map[string]any{"load_type": "percentage", "load_value": "bad"}}}}}, false)
	if err != nil {
		t.Fatal(err)
	}
	meta := got["meta"].(map[string]any)
	if _, ok := meta["name"]; ok {
		t.Fatal("update invented a name")
	}
	session := got["sessions"].([]any)[0].(map[string]any)
	if session["day_of_week"] != "Sunday" {
		t.Fatalf("unexpected weekday: %#v", session)
	}
	exercise := session["exercises"].([]any)[0].(map[string]any)
	if exercise["load_type"] != "unresolvable" || exercise["load_value"] != nil {
		t.Fatalf("unexpected prescription: %#v", exercise)
	}
}

func TestPrepareRetainsTimedPrescriptions(t *testing.T) {
	input := map[string]any{"sessions": []any{map[string]any{"exercises": []any{map[string]any{"name": "Bike", "rep_unit": "minutes", "reps": 15, "load_type": "duration"}}}}}
	got, err := Prepare(input, true)
	if err != nil {
		t.Fatal(err)
	}
	exercise := got["sessions"].([]any)[0].(map[string]any)["exercises"].([]any)[0].(map[string]any)
	if exercise["load_type"] != "duration" || exercise["rep_unit"] != "minutes" {
		t.Fatalf("exercise = %#v", exercise)
	}
}
