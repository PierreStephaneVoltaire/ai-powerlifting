package activities

import (
	"context"
	"sort"
	"strings"

	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

const summaryRunes = 200

func requiredPermissions(operations []string) []string {
	seen := map[string]bool{}
	for _, name := range operations {
		if permission := tools.Permission(name); permission != "" {
			seen[permission] = true
		}
	}
	permissions := make([]string, 0, len(seen))
	for permission := range seen {
		permissions = append(permissions, permission)
	}
	sort.Strings(permissions)
	return permissions
}

func summarize(reply string) string {
	flat := strings.Join(strings.Fields(reply), " ")
	runes := []rune(flat)
	if len(runes) <= summaryRunes {
		return flat
	}
	return string(runes[:summaryRunes]) + "..."
}

func (d *Deps) Deliver(ctx context.Context, in DeliverInput) (struct{}, error) {
	permissions := requiredPermissions(in.UsedOperations)
	if err := d.Store.CompleteTurn(ctx, store.Completion{
		TurnID: in.TurnID, Status: in.Status, Reply: in.Reply, Summary: summarize(in.Reply), Error: in.Error, RequiredPermissions: permissions,
	}); err != nil {
		return struct{}{}, err
	}
	if in.Status != "succeeded" {
		return struct{}{}, nil
	}
	for kind, content := range map[string]string{"request": in.Request, "reply": in.Reply} {
		if strings.TrimSpace(content) == "" {
			continue
		}
		embedding, err := d.LLM.Embed(ctx, d.Config.EmbedModel, agent.Truncate(content, MaxChars))
		if err != nil || len(embedding) != d.Config.EmbedDim {
			d.Log.Warn("embedding skipped", "turn_id", in.TurnID, "kind", kind, "error", err)
			continue
		}
		if err := d.Store.InsertEmbedding(ctx, in.TurnID, in.ConversationID, in.Athlete, kind, content, permissions, embedding); err != nil {
			return struct{}{}, err
		}
	}
	return struct{}{}, nil
}
