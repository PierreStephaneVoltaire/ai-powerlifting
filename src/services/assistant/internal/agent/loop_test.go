package agent

import (
	"strings"
	"testing"

	"powerlifting/assistant/internal/llm"
)

func TestLargeModelUsageDoesNotExhaustSteps(t *testing.T) {
	var state State
	state.Record(llm.ChatResponse{PromptTokens: 1000000, CompletionTokens: 1000000})
	if err := state.Exhausted(Limits{MaxSteps: 12}); err != nil {
		t.Fatal("token usage exhausted the workflow before its step limit")
	}
}

func TestToolResultPreservesCompleteResearch(t *testing.T) {
	content := strings.Repeat("compound findings\n", 2000) + "FINAL INGREDIENT"
	var state State
	state.AddToolResult("research", content)
	if len(state.Messages) != 1 || state.Messages[0].Content != content {
		t.Fatal("tool result lost research data")
	}
}

func TestReferenceLookupIsAnInternalTool(t *testing.T) {
	call := Classify(llm.ToolCall{Function: llm.FunctionCall{Name: ReferenceTool, Arguments: `{"kind":"supplements","query":"Is ashwagandha useful?"}`}})
	if call.Kind != KindReference || call.Malformed != "" {
		t.Fatalf("reference call: %+v", call)
	}
	found := false
	for _, def := range PseudoTools(nil, 0, 1) {
		if def.Function.Name == ReferenceTool {
			found = true
		}
	}
	if !found {
		t.Fatal("reference lookup missing from coordinator tools")
	}
}
