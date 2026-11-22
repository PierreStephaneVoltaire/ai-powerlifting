package render

import (
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
)

func TestScoreTrendInBothFormats(t *testing.T) {
	bundle := map[string]any{
		"block":      map[string]any{"label": "B", "block": "b", "startDate": "2025-01-01", "endDate": "2025-01-31", "weekStart": 1.0, "weekEnd": 4.0},
		"athleteSex": "male",
		"weightLog":  []any{map[string]any{"date": "2025-01-01", "kg": 80.0}},
		"sessions": []map[string]any{
			{"date": "2025-01-02", "block": "b", "week_number": 1.0, "completed": true, "exercises": []any{map[string]any{"name": "Bench Press", "sets_data": []any{map[string]any{"kg": 100.0, "reps": 1.0, "rpe": 10.0}, map[string]any{"kg": 200.0, "reps": 1.0}}, "set_statuses": []any{"completed", "pending"}}}},
			{"date": "2025-01-03", "block": "other", "week_number": 1.0, "completed": true, "exercises": []any{map[string]any{"name": "Squat", "kg": 500.0, "reps": 1.0}}},
		},
	}
	markdown := BlockMarkdown(bundle, time.Time{})
	if !strings.Contains(markdown, "| 1 |  | 100 |  | 100 | 68.95 | 51.19 | classic_bench |") {
		t.Fatalf("unexpected score table:\n%s", markdown)
	}
	content, err := BlockWorkbook(bundle)
	if err != nil {
		t.Fatal(err)
	}
	file, err := excelize.OpenReader(strings.NewReader(string(content)))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if value, _ := file.GetCellValue("e1RM and DOTS", "C2"); value != "100" {
		t.Fatalf("bench = %q", value)
	}
	if value, _ := file.GetCellValue("e1RM and DOTS", "G2"); value != "51.19" {
		t.Fatalf("IPF GL = %q", value)
	}
	delete(bundle, "weightLog")
	if strings.Contains(BlockMarkdown(bundle, time.Time{}), "68.95") {
		t.Fatal("score used unavailable bodyweight")
	}
}

func TestPlannedActualComplianceAndWeeklyChanges(t *testing.T) {
	bundle := map[string]any{
		"block":  map[string]any{"block": "b", "startDate": "2025-01-01", "endDate": "2025-01-31"},
		"weekly": map[string]any{"compliance": map[string]any{"pct": 90.0, "set_pct": 80.0, "vol_pct": 70.0}},
		"sessions": []map[string]any{
			{"date": "2025-01-02", "block": "b", "week_number": 1.0, "completed": true, "planned_exercises": []any{map[string]any{"name": "Squat", "sets": 2.0, "reps": 1.0, "kg": 105.0, "rpe_target": 8.0}}, "exercises": []any{map[string]any{"name": "Squat", "sets_data": []any{map[string]any{"kg": 100.0, "reps": 1.0, "rpe": 10.0}, map[string]any{"kg": 95.0, "reps": 1.0, "rpe": 9.0}}, "set_statuses": []any{"completed", "completed"}}}},
			{"date": "2025-01-09", "block": "b", "week_number": 2.0, "completed": true, "exercises": []any{map[string]any{"name": "Squat", "sets": 1.0, "kg": 110.0, "reps": 1.0, "rpe": 10.0}}},
		},
	}
	markdown := BlockMarkdown(bundle, time.Time{})
	for _, expected := range []string{"| Set compliance | 80.0% |", "| Volume compliance | 70.0% |", "| Planned | 2 x 1 | 105.0 kg | 8.0 |", "| Actual | 1 x 1 | 95.0 kg | 9.0 |"} {
		if !strings.Contains(markdown, expected) {
			t.Fatalf("missing %q in %s", expected, markdown)
		}
	}
	rows := newBlock(bundle).scoreTrendRows()
	if rows[1][8] != nil || rows[2][8] != 10.0 || rows[2][9] != nil {
		t.Fatalf("unexpected deltas: %v", rows)
	}
	content, err := BlockWorkbook(bundle)
	if err != nil {
		t.Fatal(err)
	}
	file, err := excelize.OpenReader(strings.NewReader(string(content)))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if value, _ := file.GetCellValue("e1RM and DOTS", "I3"); value != "10" {
		t.Fatalf("squat change = %q", value)
	}
}
