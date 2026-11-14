package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"

	"powerlifting/analytics-ai/internal/pyjson"
)

type KV interface {
	Get(ctx context.Context, key string) (string, bool, error)
	Set(ctx context.Context, key, value string, ttl time.Duration) error
}

type Redis struct{ Client redis.Cmdable }

func (r Redis) Get(ctx context.Context, key string) (string, bool, error) {
	value, err := r.Client.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	return value, err == nil, err
}

func (r Redis) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return r.Client.Set(ctx, key, value, ttl).Err()
}

type Request struct {
	Messages       []any
	Tools          []any
	ResponseFormat any
}

func (r Request) value() map[string]any {
	var messages, tools any
	if r.Messages != nil {
		messages = r.Messages
	}
	if r.Tools != nil {
		tools = r.Tools
	}
	return map[string]any{"messages": messages, "tools": tools, "response_format": r.ResponseFormat}
}

func (r Request) Hash() (string, error) {
	encoded, err := pyjson.Encode(r.value())
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func AnalysisVersion(ctx context.Context, kv KV, athlete string) string {
	value, found, err := kv.Get(ctx, "pl:analysis-version:"+athlete)
	if err != nil {
		slog.Warn("analysis version read failed", "error", err)
		return "0"
	}
	if !found || value == "" {
		return "0"
	}
	return value
}
