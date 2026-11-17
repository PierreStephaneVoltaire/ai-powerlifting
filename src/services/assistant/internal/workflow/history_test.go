package workflow

import (
	"strings"
	"testing"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
)

func TestHistoryMarkdownKeepsCompleteContentAndCursor(t *testing.T) {
	content := strings.Repeat("ingredient findings\n", 2000) + "FINAL INGREDIENT"
	history := activities.HistoryOutput{Messages: []llm.Message{{Role: "assistant", Content: content}}, NextBefore: "older-turn"}
	text := historyMarkdown(history)
	if !strings.Contains(text, content) || !strings.Contains(text, "before_turn=older-turn") {
		t.Fatal("Markdown history lost content or its cursor")
	}
	history.NextBefore = ""
	if !strings.Contains(historyMarkdown(history), "End of accessible conversation history.") {
		t.Fatal("history did not identify the end")
	}
}
