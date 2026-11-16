package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("not found")

type Store struct {
	Pool *pgxpool.Pool
}

type ConnConfig struct {
	Host, Port, Database, User, Password, SSLMode string
}

func (c ConnConfig) DSN() string {
	return (&url.URL{
		Scheme:   "postgres",
		User:     url.UserPassword(c.User, c.Password),
		Host:     c.Host + ":" + c.Port,
		Path:     c.Database,
		RawQuery: url.Values{"sslmode": {c.SSLMode}}.Encode(),
	}).String()
}

func Open(ctx context.Context, config ConnConfig, dim int) (*Store, error) {
	pool, err := pgxpool.New(ctx, config.DSN())
	if err != nil {
		return nil, err
	}
	store := &Store{Pool: pool}
	if err := store.Bootstrap(ctx, dim); err != nil {
		pool.Close()
		return nil, err
	}
	return store, nil
}

func (s *Store) Close() {
	s.Pool.Close()
}

func (s *Store) Ping(ctx context.Context) error {
	return s.Pool.Ping(ctx)
}

func (s *Store) Bootstrap(ctx context.Context, dim int) error {
	conn, err := s.Pool.Acquire(ctx)
	if err != nil {
		return err
	}
	defer conn.Release()
	if _, err := conn.Exec(ctx, "SELECT pg_advisory_lock($1)", bootstrapLock); err != nil {
		return err
	}
	defer conn.Exec(context.WithoutCancel(ctx), "SELECT pg_advisory_unlock($1)", bootstrapLock)
	for _, statement := range schema(dim) {
		if _, err := conn.Exec(ctx, statement); err != nil {
			return fmt.Errorf("bootstrap: %w", err)
		}
	}
	return nil
}

func (s *Store) EnsureConversation(ctx context.Context, ref ConversationRef, person string) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `INSERT INTO conversations (id, athlete_pk, kind, shared, owner_person, scope)
		VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO UPDATE SET updated_at = now()`,
		ref.ID, ref.Athlete, ref.Kind, ref.Shared, ref.Owner, ref.Scope); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO participants (conversation_id, person_pk) VALUES ($1,$2)
		ON CONFLICT (conversation_id, person_pk) DO UPDATE SET last_seen = now()`, ref.ID, person); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *Store) Participants(ctx context.Context, conversationID string) ([]string, error) {
	rows, err := s.Pool.Query(ctx, `SELECT person_pk FROM participants WHERE conversation_id=$1 ORDER BY person_pk`, conversationID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var people []string
	for rows.Next() {
		var person string
		if err := rows.Scan(&person); err != nil {
			return nil, err
		}
		people = append(people, person)
	}
	return people, rows.Err()
}

func (s *Store) IsParticipant(ctx context.Context, conversationID, person string) (bool, error) {
	var found bool
	err := s.Pool.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM participants WHERE conversation_id=$1 AND person_pk=$2)`, conversationID, person).Scan(&found)
	return found, err
}

type Turn struct {
	ID                  string          `json:"id"`
	ConversationID      string          `json:"conversation_id"`
	PersonPK            string          `json:"person_pk"`
	WorkflowID          string          `json:"workflow_id"`
	Status              string          `json:"status"`
	Request             json.RawMessage `json:"request"`
	Reply               string          `json:"reply"`
	Summary             string          `json:"summary"`
	Error               string          `json:"error"`
	RequiredPermissions []string        `json:"required_permissions"`
	CreatedAt           time.Time       `json:"created_at"`
	UpdatedAt           time.Time       `json:"updated_at"`
}

func (s *Store) InsertTurn(ctx context.Context, turn Turn) error {
	_, err := s.Pool.Exec(ctx, `INSERT INTO turns (id, conversation_id, person_pk, workflow_id, status, request)
		VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO NOTHING`,
		turn.ID, turn.ConversationID, turn.PersonPK, turn.WorkflowID, turn.Status, turn.Request)
	return err
}

func (s *Store) Turn(ctx context.Context, id string) (Turn, error) {
	var turn Turn
	err := s.Pool.QueryRow(ctx, `SELECT id, conversation_id, person_pk, workflow_id, status, request, reply, summary, error, required_permissions, created_at, updated_at
		FROM turns WHERE id=$1`, id).Scan(&turn.ID, &turn.ConversationID, &turn.PersonPK, &turn.WorkflowID, &turn.Status, &turn.Request, &turn.Reply, &turn.Summary, &turn.Error, &turn.RequiredPermissions, &turn.CreatedAt, &turn.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Turn{}, ErrNotFound
	}
	return turn, err
}

func (s *Store) SetTurnStatus(ctx context.Context, id, status string) error {
	_, err := s.Pool.Exec(ctx, `UPDATE turns SET status=$2, updated_at=now() WHERE id=$1 AND status IN ('queued','running')`, id, status)
	return err
}

type Completion struct {
	TurnID              string
	Status              string
	Reply               string
	Summary             string
	Error               string
	RequiredPermissions []string
}

func (s *Store) CompleteTurn(ctx context.Context, done Completion) error {
	permissions := done.RequiredPermissions
	if permissions == nil {
		permissions = []string{}
	}
	_, err := s.Pool.Exec(ctx, `UPDATE turns SET status=$2, reply=$3, summary=$4, error=$5, required_permissions=$6, updated_at=now()
		WHERE id=$1 AND status NOT IN ('cancelled')`,
		done.TurnID, done.Status, done.Reply, done.Summary, done.Error, permissions)
	if err == nil {
		_ = s.ClearProgress(ctx, done.TurnID)
	}
	return err
}

type HistoryTurn struct {
	ID        string          `json:"id"`
	PersonPK  string          `json:"person_pk"`
	Status    string          `json:"status"`
	Request   json.RawMessage `json:"request"`
	Reply     string          `json:"reply"`
	Summary   string          `json:"summary"`
	Error     string          `json:"error"`
	CreatedAt time.Time       `json:"created_at"`

	RequiredPermissions []string `json:"required_permissions"`
	Shared              bool     `json:"shared"`
}

func (s *Store) History(ctx context.Context, query HistoryQuery) ([]HistoryTurn, error) {
	sql, args := BuildHistory(query)
	rows, err := s.Pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var turns []HistoryTurn
	for rows.Next() {
		var turn HistoryTurn
		if err := rows.Scan(&turn.ID, &turn.PersonPK, &turn.Status, &turn.Request, &turn.Reply, &turn.Summary, &turn.Error, &turn.CreatedAt, &turn.RequiredPermissions, &turn.Shared); err != nil {
			return nil, err
		}
		turns = append(turns, turn)
	}
	return turns, rows.Err()
}

type Snippet struct {
	TurnID         string    `json:"turn_id"`
	ConversationID string    `json:"conversation_id"`
	Kind           string    `json:"kind"`
	Content        string    `json:"content"`
	At             time.Time `json:"at"`
	Permissions    []string  `json:"permissions"`
}

func (s *Store) Retrieve(ctx context.Context, query RetrievalQuery) ([]Snippet, error) {
	sql, args := BuildRetrieval(query)
	rows, err := s.Pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var snippets []Snippet
	for rows.Next() {
		var snippet Snippet
		if err := rows.Scan(&snippet.TurnID, &snippet.ConversationID, &snippet.Kind, &snippet.Content, &snippet.At, &snippet.Permissions); err != nil {
			return nil, err
		}
		snippets = append(snippets, snippet)
	}
	return snippets, rows.Err()
}

func (s *Store) InsertEmbedding(ctx context.Context, turnID, conversationID, athlete, kind, content string, permissions []string, embedding []float32) error {
	if permissions == nil {
		permissions = []string{}
	}
	_, err := s.Pool.Exec(ctx, `INSERT INTO embeddings (turn_id, conversation_id, athlete_pk, kind, content, required_permissions, embedding)
		VALUES ($1,$2,$3,$4,$5,$6,$7::vector) ON CONFLICT (turn_id, kind) DO NOTHING`, turnID, conversationID, athlete, kind, content, permissions, VectorLiteral(embedding))
	return err
}

func (s *Store) RateHit(ctx context.Context, person string, at time.Time) (int, error) {
	var hits int
	err := s.Pool.QueryRow(ctx, `INSERT INTO rate_counters (person_pk, window_start, hits) VALUES ($1, date_trunc('minute', $2::timestamptz), 1)
		ON CONFLICT (person_pk, window_start) DO UPDATE SET hits = rate_counters.hits + 1 RETURNING hits`, person, at).Scan(&hits)
	return hits, err
}

func (s *Store) PruneRateCounters(ctx context.Context, before time.Time) error {
	_, err := s.Pool.Exec(ctx, `DELETE FROM rate_counters WHERE window_start < $1`, before)
	return err
}

func (s *Store) CancelTurn(ctx context.Context, id string) error {
	_, err := s.Pool.Exec(ctx, `UPDATE turns SET status='cancelled', updated_at=now() WHERE id=$1 AND status IN ('queued','running')`, id)
	if err == nil {
		_ = s.ClearProgress(ctx, id)
	}
	return err
}
