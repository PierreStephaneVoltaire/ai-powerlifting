package store

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

type Progress struct {
	Stage     string
	Text      string
	UpdatedAt time.Time
}

func (s *Store) AppendProgress(ctx context.Context, turnID, stage, text string) error {
	_, err := s.Pool.Exec(ctx, `INSERT INTO turn_progress (turn_id, stage, text, updated_at) VALUES ($1,$2,$3,now())
		ON CONFLICT (turn_id) DO UPDATE SET stage=EXCLUDED.stage, text=turn_progress.text || EXCLUDED.text, updated_at=now()`, turnID, stage, text)
	return err
}

func (s *Store) Progress(ctx context.Context, turnID string) (*Progress, error) {
	var progress Progress
	err := s.Pool.QueryRow(ctx, `SELECT stage, text, updated_at FROM turn_progress WHERE turn_id=$1`, turnID).Scan(&progress.Stage, &progress.Text, &progress.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	return &progress, nil
}
