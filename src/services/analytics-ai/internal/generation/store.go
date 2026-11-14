package generation

import (
	"context"
	"encoding/json"
	"time"
)

const StatusDone = "succeeded"

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
	Requirements map[string]any
	Error        any
	Fingerprint  string
}

type Store struct {
	Athlete string
	Backend Backend
	Now     func() time.Time
}

func toInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case json.Number:
		number, _ := typed.Int64()
		return int(number)
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
		Requirements: requirements,
		Error:        item["error"],
		Fingerprint:  text(item["source_fingerprint"]),
	}
}

func (s Store) Get(ctx context.Context, id string) (*Record, error) {
	item, err := s.Backend.Get(ctx, s.Athlete, id)
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
		"athlete": s.Athlete, "generation_id": id, "source_fingerprint": id, "operation": operation,
		"owner": owner, "status": "starting", "attempt": attempt, "updated_at": s.Now().Unix(),
		"access_requirements": requirements,
	}
	if requirements == nil {
		item["access_requirements"] = nil
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
	return s.Backend.Update(ctx, s.Athlete, id, attempt, fields)
}

func (s Store) Complete(ctx context.Context, id string, result any, attempt int) error {
	return s.Backend.Save(ctx, s.Athlete, id, attempt, Item{"status": StatusDone, "updated_at": s.Now().Unix()}, result)
}

func (s Store) Result(ctx context.Context, rec *Record) (any, error) {
	value, err := s.Backend.Result(ctx, s.Athlete, rec.ID)
	if err != nil {
		return nil, err
	}
	if value == nil {
		return nil, ErrIncomplete
	}
	if object, ok := value.(map[string]any); ok {
		object["cached"] = true
	}
	return value, nil
}
