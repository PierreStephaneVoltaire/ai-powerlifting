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
