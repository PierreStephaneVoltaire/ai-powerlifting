package store

import (
	"context"
	"time"
)

type ConversationSummary struct {
	ID        string    `json:"id"`
	Kind      string    `json:"kind"`
	Shared    bool      `json:"shared"`
	Scope     string    `json:"scope"`
	UpdatedAt time.Time `json:"updated_at"`
	Label     string    `json:"label"`
}

const listGeneralConversations = `SELECT c.id, c.kind, c.shared, c.scope, c.updated_at,
	COALESCE((SELECT t.summary FROM turns t WHERE t.conversation_id = c.id AND t.required_permissions <@ $3::text[] ORDER BY t.created_at DESC LIMIT 1), '')
FROM conversations c
WHERE ` + visibleConversation + `
	AND ((c.kind = 'web' AND c.scope = 'general') OR c.kind = 'discord')
ORDER BY c.updated_at DESC
LIMIT 100`

func (s *Store) ListGeneralConversations(ctx context.Context, athlete, person string, permissions []string) ([]ConversationSummary, error) {
	if permissions == nil {
		permissions = []string{}
	}
	rows, err := s.Pool.Query(ctx, listGeneralConversations, athlete, person, permissions)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ConversationSummary{}
	for rows.Next() {
		var item ConversationSummary
		if err := rows.Scan(&item.ID, &item.Kind, &item.Shared, &item.Scope, &item.UpdatedAt, &item.Label); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}
