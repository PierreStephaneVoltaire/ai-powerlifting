package store

import (
	"context"
	"encoding/json"
	"slices"
	"time"
)

type OrchestrationEvent struct {
	Kind           string
	PersonPK       string
	ConversationID string
	WorkflowID     string
	Model          string
	Outcome        string
	Detail         map[string]any
}

func (s *Store) InsertOrchestrationEvent(ctx context.Context, event OrchestrationEvent) error {
	detail, err := json.Marshal(event.Detail)
	if err != nil || event.Detail == nil {
		detail = []byte("{}")
	}
	_, err = s.Pool.Exec(ctx, `INSERT INTO orchestration_events (kind, person_pk, conversation_id, workflow_id, model, outcome, detail)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`, event.Kind, event.PersonPK, event.ConversationID, event.WorkflowID, event.Model, event.Outcome, detail)
	return err
}

type ActivityEvent struct {
	At      time.Time
	Kind    string
	Model   string
	Outcome string
	Web     bool
}

func (s *Store) RecentActivity(ctx context.Context, personPK, workflowID string, limit int) ([]ActivityEvent, error) {
	rows, err := s.Pool.Query(ctx, `SELECT at, kind, model, outcome, COALESCE((detail->>'web')::boolean, false)
		FROM orchestration_events WHERE workflow_id=$1 AND person_pk=$2 AND kind <> 'history_unavailable'
		ORDER BY id DESC LIMIT $3`, workflowID, personPK, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	events := []ActivityEvent{}
	for rows.Next() {
		var event ActivityEvent
		if err := rows.Scan(&event.At, &event.Kind, &event.Model, &event.Outcome, &event.Web); err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	slices.Reverse(events)
	return events, rows.Err()
}
