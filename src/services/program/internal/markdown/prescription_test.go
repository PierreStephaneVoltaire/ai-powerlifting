package markdown

import "testing"

func TestTimedAndAmrapPrescriptions(t *testing.T) {
	tests := []struct {
		exercise M
		want     string
	}{
		{M{"sets": 1, "duration_minutes": 15}, "1 x 15 min"},
		{M{"sets": 2, "reps": 45, "rep_unit": "seconds"}, "2 x 45 sec"},
		{M{"sets": 2, "rep_mode": "amrap"}, "2 x AMRAP"},
		{M{"sets": 2, "rep_mode": "amrap", "reps": 10}, "2 x AMRAP (10)"},
	}
	for _, tc := range tests {
		if got := prescription(tc.exercise); got != tc.want {
			t.Errorf("prescription(%v) = %q, want %q", tc.exercise, got, tc.want)
		}
	}
}

func TestTimedWorkDoesNotContributeToDotsEstimate(t *testing.T) {
	d := sectionData{sessions: []M{{"completed": true, "week_number": 1, "exercises": []any{
		M{"name": "Squat", "kg": 100, "reps": 60, "rep_unit": "seconds"},
		M{"name": "Bench Press", "kg": 50, "reps": 5},
	}}}}
	rows := d.dotsTrendRows()
	if len(rows) != 1 || rows[0].squat != 0 || rows[0].bench == 0 {
		t.Fatalf("timed work contributed to estimates: %#v", rows)
	}
}
