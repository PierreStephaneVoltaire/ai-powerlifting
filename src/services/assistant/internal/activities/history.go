package activities

import (
	"context"
	"encoding/json"
	"slices"
	"strings"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/visibility"
)

const historyFailedReply = "[This attempt failed and produced no reply.]"
const historyTurnLimit = 5

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

func historyMessages(turn store.HistoryTurn) []llm.Message {
	request := strings.TrimSpace(requestUserText(turn.Request))
	if request == "" {
		return nil
	}
	content := request
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
		return []llm.Message{user, {Role: "assistant", Content: reply}}
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
		Permissions: in.Identity.Permissions, Before: in.TurnID, Limit: historyTurnLimit + 1,
	})
	if err != nil {
		return HistoryOutput{}, err
	}
	nextBefore := ""
	if len(turns) > historyTurnLimit {
		turns = turns[:historyTurnLimit]
		nextBefore = turns[len(turns)-1].ID
	}
	var kept [][]llm.Message
	var permissions []string
	shared := false
	for _, turn := range turns {
		shared = shared || turn.Shared
		pair := historyMessages(turn)
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
		kept = append(kept, pair)
		permissions = visibility.Union(permissions, turn.RequiredPermissions)
	}
	slices.Reverse(kept)
	var messages []llm.Message
	for _, pair := range kept {
		messages = append(messages, pair...)
	}
	return HistoryOutput{Messages: messages, Turns: len(kept), Permissions: permissions, Shared: shared, NextBefore: nextBefore}, nil
}
