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
