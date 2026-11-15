package store

import (
	"context"
	"encoding/json"
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
