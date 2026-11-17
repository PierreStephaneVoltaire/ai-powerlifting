package workflow

import (
	"strings"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/visibility"
)

func (w *Workflows) readHistory(ctx *workflow.WorkflowContext, params run, request agent.Call, result *outcome) string {
	before := turnIDOf(ctx.ID())
	if value, provided := request.Arguments["before_turn"]; provided {
		cursor, ok := value.(string)
		if !ok {
			return "error: before_turn must be a turn id"
		}
		if cursor != "" {
			before = cursor
		}
	}
	history, err := call[activities.HistoryOutput](ctx, activities.NameHistory, activities.HistoryInput{
		Identity: params.Identity, ConversationID: params.ConversationID, TurnID: before,
	}, quickRetry)
	if err != nil {
		return "error: saved conversation history could not be read: " + err.Error()
	}
	result.Permissions = visibility.Union(result.Permissions, history.Permissions)
	return historyMarkdown(history)
}

func historyMarkdown(history activities.HistoryOutput) string {
	var text strings.Builder
	text.WriteString("# Saved conversation history\n\n")
	for _, message := range history.Messages {
		text.WriteString("## " + message.Role + "\n\n" + message.Content + "\n\n")
	}
	if history.NextBefore != "" {
		text.WriteString("Older history is available. Call read_conversation_history with before_turn=" + history.NextBefore + ".\nnext_before: " + history.NextBefore)
	} else {
		text.WriteString("End of accessible conversation history.")
	}
	return text.String()
}
