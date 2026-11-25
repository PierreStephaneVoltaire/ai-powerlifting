package report

import "testing"

func TestTrendsUseRecordedBodyweightAndCompletedSets(t *testing.T) {
	sessions := []map[string]any{
		{"date": "2026-11-01", "week_number": 1.0, "completed": true, "body_weight_kg": 80.0, "exercises": []any{map[string]any{"name": "Bench Press", "kg": 80.0, "reps": 5.0, "rpe": 8.0, "sets": 1.0}}},
		{"date": "2026-11-08", "week_number": 2.0, "completed": true, "exercises": []any{map[string]any{"name": "Bench Press", "kg": 85.0, "reps": 5.0, "rpe": 8.0, "sets": 1.0}}},
		{"date": "2026-11-09", "status": "skipped", "body_weight_kg": 120.0},
	}
	rows := Trends(sessions, []map[string]any{{"date": "2026-10-30", "kg": 81.0}}, []map[string]any{{"date": "2026-11-01", "avg_protein_g": 100.0, "consistent": true}}, "male")
	if rows[1][1] != 80.0 || rows[2][1] != 81.0 {
		t.Fatalf("bodyweight trend %#v", rows[:4])
	}
	var scores [][]any
	for _, row := range rows {
		if len(row) == 12 {
			if _, ok := row[0].(int); ok {
				scores = append(scores, row)
			}
		}
	}
	if len(scores) != 2 || scores[0][2] != 98.2 || scores[1][2] != 104.3 || scores[1][5] != 80.0 || scores[1][10] != 6.1 || scores[0][7] == nil {
		t.Fatalf("scores %#v", scores)
	}
}
