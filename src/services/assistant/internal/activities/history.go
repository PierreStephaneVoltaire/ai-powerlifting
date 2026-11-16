package activities

import (
	"context"
	"encoding/json"
	"slices"
	"strings"

	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/visibility"
)

const (
	historyTurnLimit   = 20
	historyMessageCap  = 1500
	historyLatestCap   = 6000
	historyTotalCap    = 24000
	historyFailedReply = "[This attempt failed and produced no reply.]"
)

func requestUserText(request json.RawMessage) string {
	var parsed struct {
		Messages []llm.Message `json:"messages"`
	}
	if json.Unmarshal(request, &parsed) != nil {
		return ""
	}
	for index := len(parsed.Messages) - 1; index >= 0; index-- {
		if parsed.Messages[index].Role == "user" {
			return parsed.Messages[index].Content
		}
	}
	return ""
}

func historyMessages(turn store.HistoryTurn, replyCap int) []llm.Message {
	request := strings.TrimSpace(requestUserText(turn.Request))
	if request == "" {
		return nil
	}
	content := agent.Truncate(request, historyMessageCap)
	if turn.Shared {
		content = "[from " + turn.PersonPK + "] " + content
	}
	user := llm.Message{Role: "user", Content: content}
	switch turn.Status {
	case "succeeded":
		reply := strings.TrimSpace(turn.Reply)
		if reply == "" {
			return nil
		}
		return []llm.Message{user, {Role: "assistant", Content: agent.Truncate(reply, replyCap)}}
	case "failed":
		return []llm.Message{user, {Role: "assistant", Content: historyFailedReply}}
	case "queued", "running":
		return []llm.Message{user, {Role: "assistant", Content: "[This request is unfinished; proposals may still be awaiting approval. Do not assume any change was applied.]"}}
	case "cancelled":
		return []llm.Message{user, {Role: "assistant", Content: "[This request was stopped. Read the current state before retrying any changes.]"}}
	}
	return nil
}

func (d *Deps) History(ctx context.Context, in HistoryInput) (HistoryOutput, error) {
	turns, err := d.Store.History(ctx, store.HistoryQuery{
		ConversationID: in.ConversationID, Athlete: in.Identity.Athlete, Person: in.Identity.Person,
		Permissions: in.Identity.Permissions, Before: in.TurnID, Limit: historyTurnLimit,
	})
	if err != nil {
		return HistoryOutput{}, err
	}
	var kept [][]llm.Message
	var permissions []string
	size := 0
	shared := false
	replyCap := historyLatestCap
	for _, turn := range turns {
		shared = shared || turn.Shared
		pair := historyMessages(turn, replyCap)
		if len(pair) == 0 {
			continue
		}
		proposals, err := d.Store.ProposalsForTurn(ctx, turn.ID)
		if err != nil {
			return HistoryOutput{}, err
		}
		for _, proposal := range proposals {
			if !in.Identity.Has(tools.Permission(proposal.Operation)) {
				continue
			}
			pair[1].Content += "\n\nEarlier proposal (context only; read the current state before retrying): " + proposal.Operation + ", state=" + string(proposal.State) + ", arguments=" + string(proposal.Arguments)
			permissions = visibility.Union(permissions, []string{tools.Permission(proposal.Operation)})
		}
		cost := len(pair[0].Content) + len(pair[1].Content)
		if size+cost > historyTotalCap && len(kept) > 0 {
			break
		}
		size += cost
		kept = append(kept, pair)
		replyCap = historyMessageCap
		permissions = visibility.Union(permissions, turn.RequiredPermissions)
	}
	slices.Reverse(kept)
	var messages []llm.Message
	for _, pair := range kept {
		messages = append(messages, pair...)
	}
	return HistoryOutput{Messages: messages, Turns: len(kept), Permissions: permissions, Shared: shared}, nil
}
