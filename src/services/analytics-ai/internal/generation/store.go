package generation

import (
	"context"
	"fmt"
	"strings"
	"time"

	"powerlifting/analytics-ai/internal/pyjson"
)

const (
	shardSize  = 80000
	retention  = 180 * 24 * time.Hour
	StatusDone = "succeeded"
)

var terminal = map[string]bool{"succeeded": true, "failed": true, "cancelled": true, "uncertain": true}

func Terminal(status string) bool { return terminal[status] }

type Record struct {
	ID           string
	Operation    string
	Owner        string
	Status       string
	JobID        string
	Attempt      int
	UpdatedAt    int64
	Shards       int
	Requirements map[string]any
	Error        any
	Fingerprint  string
}

type Store struct {
	Athlete string
	Backend Backend
	Now     func() time.Time
}

func (s Store) pk() string { return "analysis#" + s.Athlete }

func (s Store) sk(id string) string { return "native_generation#" + id }

func (s Store) expires() int64 { return s.Now().Add(retention).Unix() }

func toInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	}
	return 0
}

func text(value any) string {
	result, _ := value.(string)
	return result
}

func record(item Item) *Record {
	if item == nil {
		return nil
	}
	requirements, _ := item["access_requirements"].(map[string]any)
	return &Record{
		ID:           text(item["generation_id"]),
		Operation:    text(item["operation"]),
		Owner:        text(item["owner"]),
		Status:       text(item["status"]),
		JobID:        text(item["job_id"]),
		Attempt:      toInt(item["attempt"]),
		UpdatedAt:    int64(toInt(item["updated_at"])),
		Shards:       toInt(item["shards"]),
		Requirements: requirements,
		Error:        item["error"],
		Fingerprint:  text(item["source_fingerprint"]),
	}
}

func (s Store) Get(ctx context.Context, id string) (*Record, error) {
	item, err := s.Backend.Get(ctx, s.pk(), s.sk(id))
	if err != nil {
		return nil, err
	}
	return record(item), nil
}

func (s Store) Reserve(ctx context.Context, id, operation, owner string, retry bool, requirements map[string]any) (*Record, bool, error) {
	current, err := s.Get(ctx, id)
	if err != nil {
		return nil, false, err
	}
	if current != nil && !(retry && terminal[current.Status]) {
		return current, false, nil
	}
	attempt := 1
	if current != nil {
		attempt = current.Attempt + 1
	}
	item := Item{
		"pk": s.pk(), "sk": s.sk(id), "generation_id": id, "source_fingerprint": id, "operation": operation,
		"owner": owner, "status": "starting", "attempt": attempt, "updated_at": s.Now().Unix(),
		"access_requirements": requirements, "expires_at": s.expires(),
	}
	var created bool
	if current == nil {
		created, err = s.Backend.PutIfAbsent(ctx, item)
	} else {
		created, err = s.Backend.PutIfCurrent(ctx, item, current.Status, current.Attempt)
	}
	if err != nil {
		return nil, false, err
	}
	if created {
		return record(item), true, nil
	}
	latest, err := s.Get(ctx, id)
	return latest, false, err
}

func (s Store) Update(ctx context.Context, id string, attempt int, fields Item) error {
	fields["updated_at"] = s.Now().Unix()
	return s.Backend.Update(ctx, s.pk(), s.sk(id), attempt, fields)
}

func (s Store) Complete(ctx context.Context, id string, result any, attempt int) error {
	payload, err := pyjson.Encode(result)
	if err != nil {
		return err
	}
	shards := 0
	for start := 0; start < len(payload) || shards == 0; start += shardSize {
		end := min(start+shardSize, len(payload))
		shard := Item{"pk": s.pk(), "sk": s.sk(fmt.Sprintf("%s#result#%d#%d", id, attempt, shards)), "payload": string(payload[start:end]), "expires_at": s.expires()}
		if err := s.Backend.Put(ctx, shard); err != nil {
			return err
		}
		shards++
	}
	return s.Update(ctx, id, attempt, Item{"status": StatusDone, "shards": shards, "expires_at": s.expires()})
}

func (s Store) Result(ctx context.Context, rec *Record) (any, error) {
	var builder strings.Builder
	if rec.Shards == 0 {
		return nil, ErrIncomplete
	}
	for index := 0; index < rec.Shards; index++ {
		shard, err := s.Backend.Get(ctx, s.pk(), s.sk(fmt.Sprintf("%s#result#%d#%d", rec.ID, rec.Attempt, index)))
		if err != nil {
			return nil, err
		}
		if shard == nil {
			return nil, ErrIncomplete
		}
		builder.WriteString(text(shard["payload"]))
	}
	value, err := pyjson.Decode([]byte(builder.String()))
	if err != nil {
		return nil, err
	}
	if object, ok := value.(map[string]any); ok {
		object["cached"] = true
	}
	return value, nil
}
