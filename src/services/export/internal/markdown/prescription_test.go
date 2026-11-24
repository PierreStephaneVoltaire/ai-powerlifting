package markdown

import (
	"testing"

	"powerlifting/export/internal/report"
)

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
	sessions := []M{{"completed": true, "week_number": 1, "exercises": []any{
		M{"name": "Squat", "sets": 1, "kg": 100, "reps": 60, "rep_unit": "seconds"},
		M{"name": "Bench Press", "sets": 1, "kg": 50, "reps": 5},
	}}}
	rows := report.LiftTrends(sessions, nil, "male")
	if len(rows) != 1 || rows[0][1] != nil || rows[0][2] == nil {
		t.Fatalf("timed work contributed to estimates: %#v", rows)
	}
}
