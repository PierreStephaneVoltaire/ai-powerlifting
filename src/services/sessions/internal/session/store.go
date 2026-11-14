package session

import (
	"context"

	"powerlifting/sessions/internal/value"
)

type Sessions interface {
	ForProgram(ctx context.Context, pk, programSK string) ([]value.Item, error)
	Listing(ctx context.Context, pk, programSK string) ([]value.Item, error)
	Put(ctx context.Context, item value.Item) error
	Delete(ctx context.Context, pk, sk string) error
	Apply(ctx context.Context, pk string, deleteSKs []string, puts []value.Item) error
}

type Program struct {
	Found       bool
	Unpublished bool
	Phases      []any
}

type Programs interface {
	CurrentSK(ctx context.Context, pk string) (string, error)
	Program(ctx context.Context, pk, sk string) (Program, error)
}
