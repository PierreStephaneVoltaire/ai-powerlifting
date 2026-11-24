package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"

	"github.com/redis/go-redis/v9"
)

type Request struct {
	Messages       []any
	Tools          []any
	ResponseFormat any
}

func (r Request) value() map[string]any {
	return map[string]any{"messages": r.Messages, "tools": r.Tools, "response_format": r.ResponseFormat}
}
func (r Request) Hash() (string, error) {
	encoded, err := json.Marshal(r.value())
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

type Versions struct{ Client redis.Cmdable }

func (v Versions) AnalysisVersion(ctx context.Context, athlete string) string {
	value, err := v.Client.Get(ctx, "pl:analysis-version:"+athlete).Result()
	if errors.Is(err, redis.Nil) || value == "" {
		return "0"
	}
	if err != nil {
		slog.Warn("analysis version read failed", "error", err)
		return "0"
	}
	return value
}
