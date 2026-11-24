package apply

import "testing"

func TestConvertBlockPreservesTimedAndAMRAP(t *testing.T) {
	program := map[string]any{"sk": "program#1", "meta": map[string]any{"program_start": "2026-09-01"}, "sessions": []any{map[string]any{"date": "2026-09-01", "day": "Tuesday", "planned_exercises": []any{map[string]any{"name": "Leg Curl", "sets": 2, "rep_mode": "amrap", "rpe_target": 7}, map[string]any{"name": "Bike", "sets": 1, "duration_minutes": 15}}}}}
	result, err := Convert(program, nil)
	if err != nil {
		t.Fatal(err)
	}
	session := result["sessions"].([]any)[0].(map[string]any)
	exercises := session["exercises"].([]any)
	curl := exercises[0].(map[string]any)
	bike := exercises[1].(map[string]any)
	if curl["rep_mode"] != "amrap" || curl["reps"] != nil || curl["load_type"] != "rpe" {
		t.Fatalf("curl: %#v", curl)
	}
	if bike["reps"] != 15.0 || bike["rep_unit"] != "minutes" || bike["load_type"] != "duration" {
		t.Fatalf("bike: %#v", bike)
	}
}
