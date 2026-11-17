package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

type Proposal struct {
	ID             string          `json:"id"`
	TurnID         string          `json:"turn_id"`
	ConversationID string          `json:"conversation_id"`
	WorkflowID     string          `json:"workflow_id"`
	AthletePK      string          `json:"athlete_pk"`
	RequesterPK    string          `json:"requester_pk"`
	Operation      string          `json:"operation"`
	Arguments      json.RawMessage `json:"arguments"`
	Summary        string          `json:"summary"`
	Diff           json.RawMessage `json:"diff"`
	TargetID       string          `json:"target_id"`
	TargetRead     json.RawMessage `json:"target_read"`
	TargetVersion  string          `json:"target_version"`
	Destructive    bool            `json:"destructive"`
	State          State           `json:"state"`
	ApproverPK     string          `json:"approver_pk"`
	CommitResult   json.RawMessage `json:"commit_result,omitempty"`
	CreatedAt      time.Time       `json:"created_at"`
}

const proposalColumns = `id, turn_id, conversation_id, workflow_id, athlete_pk, requester_pk, operation, arguments, summary, diff, target_id, target_read, target_version, destructive, state, approver_pk, commit_result, created_at`

func scanProposal(row pgx.Row) (Proposal, error) {
	var proposal Proposal
	err := row.Scan(&proposal.ID, &proposal.TurnID, &proposal.ConversationID, &proposal.WorkflowID, &proposal.AthletePK, &proposal.RequesterPK, &proposal.Operation,
		&proposal.Arguments, &proposal.Summary, &proposal.Diff, &proposal.TargetID, &proposal.TargetRead, &proposal.TargetVersion, &proposal.Destructive,
		&proposal.State, &proposal.ApproverPK, &proposal.CommitResult, &proposal.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Proposal{}, ErrNotFound
	}
	return proposal, err
}

func (s *Store) InsertProposal(ctx context.Context, proposal Proposal) error {
	_, err := s.Pool.Exec(ctx, `INSERT INTO proposals (id, turn_id, conversation_id, workflow_id, athlete_pk, requester_pk, operation, arguments, summary, diff, target_id, target_read, target_version, destructive, state)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) ON CONFLICT (id) DO NOTHING`,
		proposal.ID, proposal.TurnID, proposal.ConversationID, proposal.WorkflowID, proposal.AthletePK, proposal.RequesterPK, proposal.Operation,
		proposal.Arguments, proposal.Summary, proposal.Diff, proposal.TargetID, proposal.TargetRead, proposal.TargetVersion, proposal.Destructive, string(StatePending))
	return err
}

func (s *Store) Proposal(ctx context.Context, id string) (Proposal, error) {
	return scanProposal(s.Pool.QueryRow(ctx, `SELECT `+proposalColumns+` FROM proposals WHERE id=$1`, id))
}

func (s *Store) ProposalsForTurn(ctx context.Context, turnID string) ([]Proposal, error) {
	rows, err := s.Pool.Query(ctx, `SELECT `+proposalColumns+` FROM proposals WHERE turn_id=$1 ORDER BY created_at`, turnID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var proposals []Proposal
	for rows.Next() {
		proposal, err := scanProposal(rows)
		if err != nil {
			return nil, err
		}
		proposals = append(proposals, proposal)
	}
	return proposals, rows.Err()
}

func (s *Store) Advance(ctx context.Context, id string, event Event, approver string, result json.RawMessage) (Proposal, error) {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return Proposal{}, err
	}
	defer tx.Rollback(ctx)
	current, err := scanProposal(tx.QueryRow(ctx, `SELECT `+proposalColumns+` FROM proposals WHERE id=$1 FOR UPDATE`, id))
	if err != nil {
		return Proposal{}, err
	}
	next, err := Next(current.State, event)
	if err != nil {
		return current, err
	}
	decided := event == EventApprove || event == EventReject
	if _, err := tx.Exec(ctx, `UPDATE proposals SET state=$2,
			approver_pk = CASE WHEN $3 THEN $4 ELSE approver_pk END,
			decided_at = CASE WHEN $3 THEN now() ELSE decided_at END,
			commit_result = COALESCE($5, commit_result),
			updated_at = now() WHERE id=$1`, id, string(next), decided, approver, nullable(result)); err != nil {
		return Proposal{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Proposal{}, err
	}
	current.State = next
	if decided {
		current.ApproverPK = approver
	}
	if len(result) > 0 {
		current.CommitResult = result
	}
	return current, nil
}

func nullable(raw json.RawMessage) any {
	if len(raw) == 0 {
		return nil
	}
	return []byte(raw)
}
