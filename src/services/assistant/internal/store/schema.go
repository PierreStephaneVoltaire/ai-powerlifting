package store

import "fmt"

const bootstrapLock = 7424610001

func schema(dim int) []string {
	return []string{
		"CREATE EXTENSION IF NOT EXISTS vector",
		`CREATE TABLE IF NOT EXISTS conversations (
			id TEXT PRIMARY KEY,
			athlete_pk TEXT NOT NULL,
			kind TEXT NOT NULL,
			shared BOOLEAN NOT NULL,
			owner_person TEXT NOT NULL DEFAULT '',
			scope TEXT NOT NULL DEFAULT '',
			created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`,
		`CREATE INDEX IF NOT EXISTS conversations_athlete_idx ON conversations (athlete_pk)`,
		`CREATE TABLE IF NOT EXISTS participants (
			conversation_id TEXT NOT NULL REFERENCES conversations(id),
			person_pk TEXT NOT NULL,
			first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
			last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
			PRIMARY KEY (conversation_id, person_pk)
		)`,
		`CREATE INDEX IF NOT EXISTS participants_person_idx ON participants (person_pk)`,
		`CREATE TABLE IF NOT EXISTS turns (
			id TEXT PRIMARY KEY,
			conversation_id TEXT NOT NULL REFERENCES conversations(id),
			person_pk TEXT NOT NULL,
			workflow_id TEXT NOT NULL,
			status TEXT NOT NULL,
			request JSONB NOT NULL,
			reply TEXT NOT NULL DEFAULT '',
			summary TEXT NOT NULL DEFAULT '',
			error TEXT NOT NULL DEFAULT '',
			required_permissions TEXT[] NOT NULL DEFAULT '{}',
			created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`,
		`CREATE TABLE IF NOT EXISTS domain_jobs (
			id TEXT PRIMARY KEY,
			person_pk TEXT NOT NULL,
			athlete_pk TEXT NOT NULL,
			conversation_id TEXT NOT NULL,
			status TEXT NOT NULL,
			payload JSONB NOT NULL,
			result JSONB,
			error JSONB,
			state JSONB NOT NULL DEFAULT '{}',
			step INTEGER NOT NULL DEFAULT -1,
			in_flight BOOLEAN NOT NULL DEFAULT FALSE,
			created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`,
		`CREATE INDEX IF NOT EXISTS turns_conversation_idx ON turns (conversation_id, created_at DESC)`,
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS embeddings (
			id BIGSERIAL PRIMARY KEY,
			turn_id TEXT NOT NULL REFERENCES turns(id),
			conversation_id TEXT NOT NULL REFERENCES conversations(id),
			athlete_pk TEXT NOT NULL,
			kind TEXT NOT NULL,
			content TEXT NOT NULL,
			required_permissions TEXT[] NOT NULL DEFAULT '{}',
			embedding vector(%d) NOT NULL,
			created_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`, dim),
		`CREATE UNIQUE INDEX IF NOT EXISTS embeddings_turn_kind_idx ON embeddings (turn_id, kind)`,
		`CREATE INDEX IF NOT EXISTS embeddings_athlete_idx ON embeddings (athlete_pk, conversation_id)`,
		`CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx ON embeddings USING hnsw (embedding vector_l2_ops)`,
		`CREATE TABLE IF NOT EXISTS proposals (
			id TEXT PRIMARY KEY,
			turn_id TEXT NOT NULL,
			conversation_id TEXT NOT NULL REFERENCES conversations(id),
			workflow_id TEXT NOT NULL,
			athlete_pk TEXT NOT NULL,
			requester_pk TEXT NOT NULL,
			operation TEXT NOT NULL,
			arguments JSONB NOT NULL,
			summary TEXT NOT NULL DEFAULT '',
			diff JSONB NOT NULL,
			target_id TEXT NOT NULL,
			target_read JSONB NOT NULL,
			target_version TEXT NOT NULL,
			destructive BOOLEAN NOT NULL,
			state TEXT NOT NULL,
			approver_pk TEXT NOT NULL DEFAULT '',
			decided_at TIMESTAMPTZ,
			commit_result JSONB,
			created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`,
		`CREATE INDEX IF NOT EXISTS proposals_turn_idx ON proposals (turn_id)`,
		`CREATE TABLE IF NOT EXISTS rate_counters (
			person_pk TEXT NOT NULL,
			window_start TIMESTAMPTZ NOT NULL,
			hits INTEGER NOT NULL,
			PRIMARY KEY (person_pk, window_start)
		)`,
		`CREATE TABLE IF NOT EXISTS audit (
			id BIGSERIAL PRIMARY KEY,
			at TIMESTAMPTZ NOT NULL DEFAULT now(),
			kind TEXT NOT NULL,
			person_pk TEXT NOT NULL DEFAULT '',
			athlete_pk TEXT NOT NULL DEFAULT '',
			conversation_id TEXT NOT NULL DEFAULT '',
			workflow_id TEXT NOT NULL DEFAULT '',
			jti TEXT NOT NULL DEFAULT '',
			operation TEXT NOT NULL DEFAULT '',
			decision TEXT NOT NULL DEFAULT '',
			detail JSONB NOT NULL DEFAULT '{}'
		)`,
		`CREATE INDEX IF NOT EXISTS audit_conversation_idx ON audit (conversation_id, at)`,
		`CREATE TABLE IF NOT EXISTS orchestration_events (
			id BIGSERIAL PRIMARY KEY,
			at TIMESTAMPTZ NOT NULL DEFAULT now(),
			kind TEXT NOT NULL,
			person_pk TEXT NOT NULL DEFAULT '',
			conversation_id TEXT NOT NULL DEFAULT '',
			workflow_id TEXT NOT NULL DEFAULT '',
			model TEXT NOT NULL DEFAULT '',
			outcome TEXT NOT NULL DEFAULT '',
			detail JSONB NOT NULL DEFAULT '{}'
		)`,
		`CREATE INDEX IF NOT EXISTS orchestration_events_conversation_idx ON orchestration_events (conversation_id, at)`,
		`CREATE TABLE IF NOT EXISTS turn_progress (
			turn_id TEXT PRIMARY KEY,
			stage TEXT NOT NULL DEFAULT '',
			text TEXT NOT NULL DEFAULT '',
			updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`,
		`CREATE OR REPLACE FUNCTION audit_append_only() RETURNS trigger AS $$
		BEGIN
			RAISE EXCEPTION 'audit is append-only';
		END;
		$$ LANGUAGE plpgsql`,
		`DROP TRIGGER IF EXISTS audit_no_mutation ON audit`,
		`CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION audit_append_only()`,
	}
}
