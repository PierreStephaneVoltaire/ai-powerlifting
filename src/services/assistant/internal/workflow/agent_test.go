package workflow

import (
	"strings"
	"testing"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/orchestration"
)

func TestBudgetFallbackDoesNotRepeatEarlierReply(t *testing.T) {
	messages := []llm.Message{{Role: "assistant", Content: "old truncation error"}, {Role: "user", Content: "try again"}, {Role: "assistant", ToolCalls: []llm.ToolCall{{ID: "research"}}}, {Role: "tool", Content: "complete research"}}
	if got := lastAssistantText(messages, budgetText); got != budgetText {
		t.Fatalf("budget fallback repeated stale reply: %q", got)
	}
}

func TestDelegationReportsCommittedTemplateUpdateDespiteConflictingReply(t *testing.T) {
	output := SubagentOutput{
		Reply:          "I could not make the update.",
		UsedOperations: []string{"template_get", "template_update"},
		Proposals:      []string{"proposal-1"},
	}
	header := delegationResultHeader(5, orchestration.TierStrong, output)
	if !strings.Contains(header, "Confirmed committed operations: template_update") || strings.Contains(header, "template_get") {
		t.Fatalf("coordinator did not receive the confirmed write outcome: %q", header)
	}
	output.UsedOperations = []string{"template_get"}
	if strings.Contains(delegationResultHeader(5, orchestration.TierStrong, output), "committed") {
		t.Fatal("a proposal alone is not a committed write")
	}
}
