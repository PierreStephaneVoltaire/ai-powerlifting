package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"

	"powerlifting/prompt-cache/internal/entry"
)

type Valkey struct {
	Client redis.Cmdable
	TTL    time.Duration
}

func ExactKey(athlete, operation, analysisVersion, hash string) string {
	return "pl:ai-cache:exact:" + athlete + ":" + operation + ":" + analysisVersion + ":" + hash
}

func EntryKey(id string) string {
	return "pl:ai-cache:entry:" + id
}

func (v Valkey) ExactID(ctx context.Context, athlete, operation, analysisVersion, hash string) (string, bool, error) {
	id, err := v.Client.Get(ctx, ExactKey(athlete, operation, analysisVersion, hash)).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	return id, err == nil, err
}

func (v Valkey) Entry(ctx context.Context, id string) (entry.Entry, bool, error) {
	raw, err := v.Client.Get(ctx, EntryKey(id)).Bytes()
	if errors.Is(err, redis.Nil) {
		return entry.Entry{}, false, nil
	}
	if err != nil {
		return entry.Entry{}, false, err
	}
	var found entry.Entry
	if err := json.Unmarshal(raw, &found); err != nil {
		return entry.Entry{}, false, err
	}
	return found, true, nil
}

func (v Valkey) Save(ctx context.Context, saved entry.Entry, hash string) error {
	encoded, err := json.Marshal(saved)
	if err != nil {
		return err
	}
	pipe := v.Client.Pipeline()
	pipe.Set(ctx, EntryKey(saved.ID), encoded, v.TTL)
	pipe.Set(ctx, ExactKey(saved.Athlete, saved.Operation, saved.Context.AnalysisVersion, hash), saved.ID, v.TTL)
	_, err = pipe.Exec(ctx)
	return err
}
