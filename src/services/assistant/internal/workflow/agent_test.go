package workflow

import (
	"testing"

	"powerlifting/assistant/internal/llm"
)

func TestBudgetFallbackDoesNotRepeatEarlierReply(t *testing.T) {
	messages := []llm.Message{{Role: "assistant", Content: "old truncation error"}, {Role: "user", Content: "try again"}, {Role: "assistant", ToolCalls: []llm.ToolCall{{ID: "research"}}}, {Role: "tool", Content: "complete research"}}
	if got := lastAssistantText(messages, budgetText); got != budgetText {
		t.Fatalf("budget fallback repeated stale reply: %q", got)
	}
}
