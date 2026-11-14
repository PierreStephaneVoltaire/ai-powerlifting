package store

import (
	"context"

	"github.com/redis/go-redis/v9"
)

type Valkey struct{ Client redis.Cmdable }

func (v Valkey) Bump(ctx context.Context, athlete string) error {
	return v.Client.Incr(ctx, AnalysisVersionPK+athlete).Err()
}
