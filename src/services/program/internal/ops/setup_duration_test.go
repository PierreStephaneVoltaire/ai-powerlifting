package ops

import "testing"

func TestConcreteExercisePreservesDurationAndLoadTargets(t *testing.T) {
	cases := []struct {
		name       string
		exercise   map[string]any
		wantUnit   any
		wantReps   any
		wantKg     any
		wantSource string
	}{
		{"legacy", map[string]any{"duration_minutes": 15, "load_type": "unresolvable"}, "minutes", 15, nil, "duration"},
		{"seconds rpe", map[string]any{"rep_unit": "seconds", "reps": 45, "load_type": "rpe", "load_value": 8}, "seconds", 45, nil, "rpe"},
		{"loaded duration", map[string]any{"rep_unit": "minutes", "reps": 2, "load_type": "absolute", "load_value": 20}, "minutes", 2, 20, "absolute"},
		{"amrap", map[string]any{"rep_mode": "amrap", "load_type": "rpe", "rpe_target": 8}, nil, nil, nil, "rpe"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tc.exercise["name"], tc.exercise["glossary_id"] = "Carry", "carry"
			got := concreteExercise(tc.exercise, map[string]float64{"carry": 100})
			if got["rep_unit"] != tc.wantUnit || got["reps"] != tc.wantReps || got["kg"] != tc.wantKg || got["load_source"] != tc.wantSource {
				t.Fatalf("prescription lost: %#v", got)
			}
			if tc.name == "seconds rpe" && (got["rpe_target"] != 8 || got["load_value"] != 8) {
				t.Fatalf("timed RPE lost: %#v", got)
			}
			if tc.name == "amrap" && (got["rep_mode"] != "amrap" || got["rpe_target"] != 8) {
				t.Fatalf("AMRAP lost: %#v", got)
			}
		})
	}
}

func TestRpeWithoutMaxRemainsAvailable(t *testing.T) {
	got := concreteExercise(map[string]any{"name": "Curl", "reps": 8, "load_type": "rpe", "load_value": 8}, nil)
	if got["kg"] != nil || got["load_source"] != "rpe" || got["rpe_target"] != 8 {
		t.Fatalf("RPE target lost: %#v", got)
	}
}
