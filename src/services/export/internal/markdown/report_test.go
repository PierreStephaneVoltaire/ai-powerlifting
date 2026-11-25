package markdown

import (
	"strings"
	"testing"
)

func TestReportIncludesDetailedAnalysisTables(t *testing.T) {
	text, err := Render(Input{Program: M{"meta": M{"height_cm": 181.0}, "diet_notes": []any{M{"date": "2026-11-06", "avg_protein_g": 170.0}}}, Weekly: M{"readiness_score": M{"score": 74.0, "zone": "yellow"}}})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"### Readiness", "| Overall score | 74.0 |", "### Weekly Nutrition and Sleep", "### Athlete Measurements"} {
		if !strings.Contains(text, want) {
			t.Errorf("missing %q", want)
		}
	}
}

func TestReportIncludesPlanAndMeasuredTrendsWithinAnalysis(t *testing.T) {
	program := M{
		"meta":       M{"sex": "female", "current_body_weight_kg": 75},
		"diet_notes": []any{M{"date": "2026-01-05", "avg_protein_g": 150}},
		"sessions": []any{M{
			"date": "2026-01-05", "week_number": 1, "status": "completed", "body_weight_kg": 75,
			"planned_exercises": []any{M{"name": "Squat", "sets": 3, "reps": 5, "kg": 100, "rpe_target": 8}},
			"exercises":         []any{M{"name": "Squat", "sets": 3, "reps": 5, "kg": 95, "rpe": 9}},
		}},
	}
	text, err := Render(Input{Program: program})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"**Actual exercises**", "**Planned exercises**", "| Squat | 3 x 5 | 100 | 8 |", "| W1 | 112.4 |", "IPF GL", "### Body Weight Trend"} {
		if !strings.Contains(text, want) {
			t.Errorf("missing %q in %s", want, text)
		}
	}
	analysis, nutrition := strings.Index(text, "## Analysis"), strings.Index(text, "### Nutrition and Sleep")
	if analysis < 0 || nutrition < analysis {
		t.Fatalf("nutrition outside analysis: %s", text)
	}
}
