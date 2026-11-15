package people

import (
	"context"
	"strings"

	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

const identityPrefix = "Identity#"

type Repo struct {
	DB  *store.DB
	Env clock.Env
}

func (r *Repo) Get(ctx context.Context, pk string) (value.Item, error) {
	return r.DB.Get(ctx, r.DB.Tables.User, store.PK(pk))
}

func IsIdentityPointer(item value.Item) bool {
	return strings.HasPrefix(value.Str(item["pk"]), identityPrefix)
}

func (r *Repo) Record(ctx context.Context, identifier string) (value.Item, error) {
	if identifier == "" || identifier == "anonymous" {
		return nil, nil
	}
	direct, err := r.Get(ctx, identifier)
	if err != nil || direct != nil {
		return direct, err
	}
	rows, err := r.DB.Scan(ctx, store.Scan{
		Table:      r.DB.Tables.User,
		Filter:     "mapped_pk = :id",
		Values:     map[string]any{":id": identifier},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	var matches []value.Item
	for _, row := range rows {
		if !IsIdentityPointer(row) {
			matches = append(matches, row)
		}
	}
	if len(matches) != 1 {
		return nil, nil
	}
	return matches[0], nil
}

func (r *Repo) All(ctx context.Context) ([]value.Item, error) {
	rows, err := r.DB.Scan(ctx, store.Scan{Table: r.DB.Tables.User, Consistent: true})
	if err != nil {
		return nil, err
	}
	people := rows[:0]
	for _, row := range rows {
		if !IsIdentityPointer(row) {
			people = append(people, row)
		}
	}
	return people, nil
}

func (r *Repo) Update(ctx context.Context, pk string, update store.Update) error {
	return r.DB.Update(ctx, r.DB.Tables.User, store.PK(pk), update)
}

func (r *Repo) Settings(item value.Item) Settings {
	return Normalize(item, r.Env.Now(), clock.ISO)
}
