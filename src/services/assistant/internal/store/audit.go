package store

import (
	"context"
	"encoding/json"
)

type AuditEntry struct {
	Kind           string
	PersonPK       string
	AthletePK      string
	ConversationID string
	WorkflowID     string
	JTI            string
	Operation      string
	Decision       string
	Detail         map[string]any
}

func (s *Store) Audit(ctx context.Context, entry AuditEntry) error {
	detail, err := json.Marshal(entry.Detail)
	if err != nil || entry.Detail == nil {
		detail = []byte("{}")
	}
	_, err = s.Pool.Exec(ctx, `INSERT INTO audit (kind, person_pk, athlete_pk, conversation_id, workflow_id, jti, operation, decision, detail)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		entry.Kind, entry.PersonPK, entry.AthletePK, entry.ConversationID, entry.WorkflowID, entry.JTI, entry.Operation, entry.Decision, detail)
	return err
}
