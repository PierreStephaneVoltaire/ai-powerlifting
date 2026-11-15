package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"

	"github.com/redis/go-redis/v9"
)

const (
	versionPrefix = "pl:analysis-version:"
	analysisKeys  = "pl:analysis:*"
	scanBatch     = 200
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

type Valkey struct{ Client redis.Cmdable }

func (v Valkey) AnalysisVersion(ctx context.Context, athlete string) string {
	value, err := v.Client.Get(ctx, versionPrefix+athlete).Result()
	if errors.Is(err, redis.Nil) || value == "" {
		return "0"
	}
	if err != nil {
		slog.Warn("analysis version read failed", "error", err)
		return "0"
	}
	return value
}

func (v Valkey) BumpAnalysis(ctx context.Context, athlete string) {
	if err := v.Client.Incr(ctx, versionPrefix+athlete).Err(); err != nil {
		slog.Error("analysis version bump failed", "athlete", athlete, "error", err)
	}
}

func (v Valkey) InvalidateGlossary(ctx context.Context, athlete string) {
	v.dropDomain(ctx, "pl:cache:"+athlete+":domain:glossary")
}

func (v Valkey) InvalidateCatalog(ctx context.Context) {
	v.sweep(ctx, analysisKeys)
	v.bumpAll(ctx)
	v.InvalidateAllGlossaries(ctx)
}

func (v Valkey) sweep(ctx context.Context, pattern string) {
	var batch []string
	flush := func() {
		if len(batch) == 0 {
			return
		}
		if err := v.Client.Unlink(ctx, batch...).Err(); err != nil {
			slog.Warn("analysis sweep failed", "error", err)
		}
		batch = batch[:0]
	}
	iterator := v.Client.Scan(ctx, 0, pattern, scanBatch).Iterator()
	for iterator.Next(ctx) {
		batch = append(batch, iterator.Val())
		if len(batch) >= scanBatch {
			flush()
		}
	}
	flush()
	if err := iterator.Err(); err != nil {
		slog.Warn("analysis sweep scan failed", "error", err)
	}
}

func (v Valkey) bumpAll(ctx context.Context) {
	iterator := v.Client.Scan(ctx, 0, versionPrefix+"*", scanBatch).Iterator()
	for iterator.Next(ctx) {
		if err := v.Client.Incr(ctx, iterator.Val()).Err(); err != nil {
			slog.Warn("analysis version bump failed", "key", iterator.Val(), "error", err)
		}
	}
	if err := iterator.Err(); err != nil {
		slog.Warn("analysis version scan failed", "error", err)
	}
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
