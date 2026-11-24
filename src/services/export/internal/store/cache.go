package store

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/redis/go-redis/v9"
)

type Cache struct{ Client redis.Cmdable }

func (v Cache) Bump(ctx context.Context, athlete string) error {
	return v.Client.Incr(ctx, "pl:analysis-version:"+athlete).Err()
}

func (v Cache) Version(ctx context.Context, athlete string) (string, error) {
	value, err := v.Client.Get(ctx, "pl:analysis-version:"+athlete).Result()
	if errors.Is(err, redis.Nil) {
		return "0", nil
	}
	return value, err
}

func (v Cache) Get(ctx context.Context, key string) (map[string]any, error) {
	value, err := v.Client.Get(ctx, key).Bytes()
	if errors.Is(err, redis.Nil) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var record map[string]any
	if err := json.Unmarshal(value, &record); err != nil {
		return nil, err
	}
	return record, nil
}

func (v Cache) Set(ctx context.Context, key string, record map[string]any) error {
	value, err := json.Marshal(record)
	if err != nil {
		return err
	}
	return v.Client.Set(ctx, key, value, 0).Err()
}
