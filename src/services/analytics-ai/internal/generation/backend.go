package generation

import (
	"context"
	"time"
)

type Item = map[string]any

type Backend interface {
	Get(ctx context.Context, athlete, id string) (Item, error)
	PutIfAbsent(ctx context.Context, item Item) (bool, error)
	PutIfCurrent(ctx context.Context, item Item, status string, attempt int) (bool, error)
	Update(ctx context.Context, athlete, id string, attempt int, fields Item) error
	Save(ctx context.Context, athlete, id string, attempt int, fields Item, result any) error
	Result(ctx context.Context, athlete, id string) (any, error)
}

type Pointers interface {
	Get(ctx context.Context, key string) (string, bool, error)
	SetNX(ctx context.Context, key, value string, ttl time.Duration) (bool, error)
	Swap(ctx context.Context, key, previous, next string, ttl time.Duration) (bool, error)
}

type Objects interface {
	Get(ctx context.Context, key string) ([]byte, bool, error)
	Put(ctx context.Context, key string, body []byte) error
}
