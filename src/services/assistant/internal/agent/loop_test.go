package agent

import (
	"strings"
	"testing"
)

func TestToolResultPreservesCompleteResearch(t *testing.T) {
	content := strings.Repeat("compound findings\n", 2000) + "FINAL INGREDIENT"
	var state State
	state.AddToolResult("research", content)
	if len(state.Messages) != 1 || state.Messages[0].Content != content {
		t.Fatal("tool result lost research data")
	}
}
