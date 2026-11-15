package store

import (
	"strconv"
	"strings"
)

const visibleConversation = `c.athlete_pk = $1 AND (
		(NOT c.shared AND c.owner_person = $2)
		OR (c.shared AND EXISTS (SELECT 1 FROM participants p WHERE p.conversation_id = c.id AND p.person_pk = $2))
	)`

type RetrievalQuery struct {
	Athlete     string
	Person      string
	Permissions []string
	Embedding   []float32
	Limit       int
}

func VectorLiteral(values []float32) string {
	var builder strings.Builder
	builder.WriteByte('[')
	for index, value := range values {
		if index > 0 {
			builder.WriteByte(',')
		}
		builder.WriteString(strconv.FormatFloat(float64(value), 'f', -1, 32))
	}
	builder.WriteByte(']')
	return builder.String()
}

func BuildRetrieval(query RetrievalQuery) (string, []any) {
	sql := `SELECT e.turn_id, e.conversation_id, e.kind, e.content, e.created_at, e.required_permissions
FROM embeddings e
JOIN conversations c ON c.id = e.conversation_id
WHERE ` + visibleConversation + `
	AND e.athlete_pk = $1
	AND e.required_permissions <@ $3::text[]
ORDER BY e.embedding <-> $4::vector
LIMIT $5`
	limit := query.Limit
	if limit <= 0 {
		limit = 5
	}
	permissions := query.Permissions
	if permissions == nil {
		permissions = []string{}
	}
	return sql, []any{query.Athlete, query.Person, permissions, VectorLiteral(query.Embedding), limit}
}

type HistoryQuery struct {
	ConversationID string
	Athlete        string
	Person         string
	Permissions    []string
	Before         string
	Limit          int
}

func BuildHistory(query HistoryQuery) (string, []any) {
	sql := `SELECT t.id, t.person_pk, t.status, t.request, t.reply, t.summary, t.error, t.created_at
FROM turns t
JOIN conversations c ON c.id = t.conversation_id
WHERE ` + visibleConversation + `
	AND c.id = $6
	AND t.required_permissions <@ $3::text[]
	AND ($4 = '' OR t.created_at < (SELECT created_at FROM turns WHERE id = $4))
ORDER BY t.created_at DESC
LIMIT $5`
	limit := query.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	permissions := query.Permissions
	if permissions == nil {
		permissions = []string{}
	}
	return sql, []any{query.Athlete, query.Person, permissions, query.Before, limit, query.ConversationID}
}
