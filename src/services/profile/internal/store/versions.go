package store

import (
	"context"
	"log/slog"

	"github.com/redis/go-redis/v9"
)

type Versions interface {
	Bump(ctx context.Context, athlete string)
}

type Valkey struct {
	Client redis.Cmdable
	Log    *slog.Logger
}

func VersionKey(athlete string) string { return "pl:analysis-version:" + athlete }

func (v Valkey) Bump(ctx context.Context, athlete string) {
	if athlete == "" {
		return
	}
	if err := v.Client.Incr(ctx, VersionKey(athlete)).Err(); err != nil && v.Log != nil {
		v.Log.Error("analysis version increment failed", "athlete", athlete, "error", err)
	}
}
