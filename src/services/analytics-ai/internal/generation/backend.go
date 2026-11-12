package generation

import "context"

type Item = map[string]any

type Backend interface {
	Get(ctx context.Context, pk, sk string) (Item, error)
	PutIfAbsent(ctx context.Context, item Item) (bool, error)
	PutIfCurrent(ctx context.Context, item Item, status string, attempt int) (bool, error)
	Put(ctx context.Context, item Item) error
	Update(ctx context.Context, pk, sk string, attempt int, fields Item) error
}
