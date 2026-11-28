package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

type DomainJob struct {
	ID, Person, Athlete, ConversationID, Status string
	Payload, Result, Error, State               json.RawMessage
	Step                                        int
	InFlight                                    bool
	CreatedAt, UpdatedAt                        time.Time
}

func (s *Store) CreateDomainJob(ctx context.Context, job DomainJob) error {
	_, err := s.Pool.Exec(ctx, `INSERT INTO domain_jobs (id, person_pk, athlete_pk, conversation_id, status, payload, state, step)
		VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, '{}'::jsonb), -1)`,
		job.ID, job.Person, job.Athlete, job.ConversationID, job.Status, job.Payload, job.State)
	return err
}

func (s *Store) DomainJob(ctx context.Context, id string) (DomainJob, error) {
	return scanDomainJob(s.Pool.QueryRow(ctx, domainJobSelect+` WHERE id=$1`, id))
}

func (s *Store) ClaimDomainStep(ctx context.Context, id string, step int) (DomainJob, bool, error) {
	job, err := scanDomainJob(s.Pool.QueryRow(ctx, `UPDATE domain_jobs SET status='running', step=$2, in_flight=TRUE, updated_at=now()
		WHERE id=$1 AND status IN ('queued','running') AND step=$2-1 AND NOT in_flight
		RETURNING `+domainJobColumns, id, step))
	if err == nil {
		return job, true, nil
	}
	if !errors.Is(err, ErrNotFound) {
		return DomainJob{}, false, err
	}
	job, err = s.DomainJob(ctx, id)
	return job, false, err
}

func (s *Store) FinishDomainStep(ctx context.Context, id string, step int, status string, state, result, failure json.RawMessage) (DomainJob, error) {
	job, err := scanDomainJob(s.Pool.QueryRow(ctx, `UPDATE domain_jobs SET step=$2, in_flight=FALSE, status=$3,
		state=COALESCE($4, state), result=COALESCE($5, result), error=COALESCE($6, error), updated_at=now()
		WHERE id=$1 AND step=$2 AND in_flight AND status='running' RETURNING `+domainJobColumns,
		id, step, status, state, result, failure))
	if !errors.Is(err, ErrNotFound) {
		return job, err
	}
	return s.DomainJob(ctx, id)
}

func (s *Store) CancelDomainJob(ctx context.Context, id string) (DomainJob, error) {
	job, err := scanDomainJob(s.Pool.QueryRow(ctx, `UPDATE domain_jobs SET status='cancelled', in_flight=FALSE,
		error='{"code":"cancelled","message":"Cancelled; check side effects before retrying"}'::jsonb, updated_at=now()
		WHERE id=$1 AND status IN ('queued','running') RETURNING `+domainJobColumns, id))
	if !errors.Is(err, ErrNotFound) {
		return job, err
	}
	return s.DomainJob(ctx, id)
}

const domainJobColumns = `id, person_pk, athlete_pk, conversation_id, status, payload, result, error, state, step, in_flight, created_at, updated_at`
const domainJobSelect = `SELECT ` + domainJobColumns + ` FROM domain_jobs`

func scanDomainJob(row pgx.Row) (DomainJob, error) {
	var job DomainJob
	err := row.Scan(&job.ID, &job.Person, &job.Athlete, &job.ConversationID, &job.Status, &job.Payload, &job.Result, &job.Error,
		&job.State, &job.Step, &job.InFlight, &job.CreatedAt, &job.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return DomainJob{}, ErrNotFound
	}
	return job, err
}
