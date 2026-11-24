package payload

import "testing"

func TestNormalizePrescription(t *testing.T) {
	tests := []struct {
		name     string
		exercise map[string]any
		wantErr  bool
		unit     string
		reps     any
		load     string
	}{
		{"legacy duration", map[string]any{"duration_minutes": "15"}, false, "minutes", 15.0, "duration"},
		{"timed rpe", map[string]any{"rep_unit": "seconds", "reps": 45, "rpe_target": 7}, false, "seconds", 45.0, "rpe"},
		{"matching units", map[string]any{"rep_unit": "seconds", "reps": 90, "duration_minutes": 1.5}, false, "seconds", 90.0, "duration"},
		{"mismatched units", map[string]any{"rep_unit": "seconds", "reps": 45, "duration_minutes": 15}, true, "", nil, ""},
		{"invalid duration", map[string]any{"duration_minutes": true}, true, "", nil, ""},
		{"amrap with reps", map[string]any{"rep_mode": "amrap", "reps": 8}, true, "", nil, ""},
		{"duration without timed unit", map[string]any{"load_type": "duration"}, true, "", nil, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := NormalizePrescription(tt.exercise)
			if (err != nil) != tt.wantErr {
				t.Fatalf("error = %v", err)
			}
			if !tt.wantErr && (tt.exercise["rep_unit"] != tt.unit || tt.exercise["reps"] != tt.reps || tt.exercise["load_type"] != tt.load) {
				t.Fatalf("unexpected exercise: %#v", tt.exercise)
			}
		})
	}
}
