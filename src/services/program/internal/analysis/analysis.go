package analysis

import (
	"context"
	"log/slog"

	"github.com/redis/go-redis/v9"
)

var inputWrites = map[string]bool{
	"block_notes_update": true, "block_transition": true, "health_invalidate_program_cache": true, "health_new_version": true,
	"health_setup_initialize": true, "program_archive": true, "program_unarchive": true,
	"program_update_meta_field": true, "program_update_phases": true,
}

func WritesAnalysisInput(operation string) bool {
	return inputWrites[operation]
}

type Versions interface {
	Record(ctx context.Context, operation, athlete string)
}

func VersionKey(athlete string) string {
	return "pl:analysis-version:" + athlete
}

type Valkey struct {
	Client redis.Cmdable
	Log    *slog.Logger
}

func (v Valkey) Record(ctx context.Context, operation, athlete string) {
	if athlete == "" || !WritesAnalysisInput(operation) {
		return
	}
	if err := v.Client.Incr(ctx, VersionKey(athlete)).Err(); err != nil {
		v.Log.Error("analysis version bump failed", "operation", operation, "error", err)
	}
}

type Noop struct{}

func (Noop) Record(context.Context, string, string) {}
