package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const ttl = 30 * 24 * time.Hour

type Request struct {
	Messages       []any
	Tools          []any
	ResponseFormat any
}

func (r Request) Hash() (string, error) {
	encoded, err := json.Marshal(map[string]any{"messages": r.Messages, "tools": r.Tools, "response_format": r.ResponseFormat})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

type Valkey struct{ Client redis.Cmdable }

func (v Valkey) key(athlete, operation, hash string) string {
	return "pl:ai-cache:exact:" + athlete + ":" + operation + ":" + hash
}

func (v Valkey) Exact(ctx context.Context, athlete, operation string, request Request) (map[string]any, bool) {
	hash, err := request.Hash()
	if err != nil {
		return nil, false
	}
	raw, err := v.Client.Get(ctx, v.key(athlete, operation, hash)).Result()
	if err != nil {
		if !errors.Is(err, redis.Nil) {
			slog.Warn("prompt cache read failed", "error", err)
		}
		return nil, false
	}
	var response map[string]any
	if json.Unmarshal([]byte(raw), &response) != nil {
		return nil, false
	}
	return response, true
}

func (v Valkey) Remember(ctx context.Context, athlete, operation string, request Request, response map[string]any) {
	hash, err := request.Hash()
	if err != nil {
		return
	}
	encoded, err := json.Marshal(response)
	if err != nil {
		return
	}
	if err := v.Client.Set(ctx, v.key(athlete, operation, hash), encoded, ttl).Err(); err != nil {
		slog.Warn("prompt cache write failed", "error", err)
	}
}

type Prompts interface {
	Exact(ctx context.Context, athlete, operation string, request Request) (map[string]any, bool)
	Remember(ctx context.Context, athlete, operation string, request Request, response map[string]any)
}

func (v Valkey) BumpAnalysis(ctx context.Context, athlete string) {
	if err := v.Client.Incr(ctx, "pl:analysis-version:"+athlete).Err(); err != nil {
		slog.Error("analysis version bump failed", "athlete", athlete, "error", err)
	}
}

func (v Valkey) InvalidateGlossary(ctx context.Context, athlete string) {
	v.dropDomain(ctx, "pl:cache:"+athlete+":domain:glossary")
}

func (v Valkey) InvalidateAllGlossaries(ctx context.Context) {
	iterator := v.Client.Scan(ctx, 0, "pl:cache:*:domain:glossary", 200).Iterator()
	for iterator.Next(ctx) {
		v.dropDomain(ctx, iterator.Val())
	}
	if err := iterator.Err(); err != nil {
		slog.Warn("glossary cache scan failed", "error", err)
	}
}

func (v Valkey) dropDomain(ctx context.Context, domainKey string) {
	items, err := v.Client.SMembers(ctx, domainKey).Result()
	if err != nil {
		slog.Warn("glossary cache invalidation failed", "error", err)
		return
	}
	keys := []string{domainKey}
	for _, item := range items {
		keys = append(keys, item, strings.Replace(item, ":item:", ":idx:", 1))
	}
	if err := v.Client.Del(ctx, keys...).Err(); err != nil {
		slog.Warn("glossary cache invalidation failed", "error", err)
	}
}
