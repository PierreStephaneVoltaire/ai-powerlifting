package attempts

import (
	"encoding/json"
	"testing"
)

func TestDefaultsAndRounding(t *testing.T) {
	result := Calculate(Request{Lift: "squat", Opener: json.Number("160")}, Preferences{})
	if result["attempt_2_kg"] != 170.0 || result["attempt_3_kg"] != 180.0 {
		t.Fatalf("%v", result)
	}
	if jumps := result["jumps_used"].(map[string]any); jumps["j1"] != json.Number("10") || jumps["j2"] != json.Number("10") {
		t.Fatalf("%v", jumps)
	}
	if warnings := result["warnings"].([]any); len(warnings) != 0 {
		t.Fatalf("%v", warnings)
	}
}

func TestRoundingIsBankers(t *testing.T) {
	if toPlate(3.75) != 5 || toPlate(1.25) != 0 || toPlate(6.25) != 5 {
		t.Fatalf("%v %v %v", toPlate(3.75), toPlate(1.25), toPlate(6.25))
	}
}

func TestPreferencesFromAProgramItem(t *testing.T) {
	prefs := PreferencesFrom(map[string]any{
		"operator_prefs": map[string]any{"attempt_jumps": map[string]any{"bench": map[string]any{"j1": 7.5}}},
		"current_maxes":  map[string]any{"bench": 120.0},
	})
	result := Calculate(Request{Lift: "bench", Opener: json.Number("100")}, prefs)
	jumps := result["jumps_used"].(map[string]any)
	if jumps["j1"] != 7.5 || jumps["j2"] != json.Number("10") {
		t.Fatalf("%v", jumps)
	}
	if result["attempt_2_kg"] != 107.5 {
		t.Fatalf("%v", result)
	}
}

func TestStoredIntegralNumbersRenderAsIntegers(t *testing.T) {
	prefs := PreferencesFrom(map[string]any{"operator_prefs": map[string]any{"attempt_jumps": map[string]any{"squat": map[string]any{"j1": 20.0, "j2": 15.0}}}})
	jumps := Calculate(Request{Lift: "squat", Opener: json.Number("100")}, prefs)["jumps_used"].(map[string]any)
	if jumps["j1"] != json.Number("20") || jumps["j2"] != json.Number("15") {
		t.Fatalf("%v", jumps)
	}
}
