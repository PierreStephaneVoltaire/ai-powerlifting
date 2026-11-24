package markdown

import (
	"strings"
	"testing"
)

func TestAIReportsIncludeFindingsAndChanges(t *testing.T) {
	text := aiReports(map[string]any{"summary": "Progress", "findings": []any{map[string]any{"driver": "Rows", "lift": "bench", "action": "Continue"}}}, map[string]any{"summary": "Stable", "small_changes": []any{map[string]any{"change": "Reduce sets", "risk": "Low"}}})
	for _, expected := range []string{"ROI Correlation", "Rows → bench", "Action: Continue", "Program Evaluation", "Reduce sets", "Risk: Low"} {
		if !strings.Contains(text, expected) {
			t.Fatalf("missing %q in %s", expected, text)
		}
	}
	if strings.Contains(text, "None") {
		t.Fatalf("nil field rendered: %s", text)
	}
}
