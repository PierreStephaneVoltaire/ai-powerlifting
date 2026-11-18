package store

import (
	"context"
	"reflect"

	"powerlifting/program/internal/pyval"
)

var supplementFields = []string{"supplements", "supplement_phases"}

func (p Programs) loadSupplements(ctx context.Context, athlete, sk string, program Item) error {
	if p.Tables.Supplements == "" {
		return nil
	}
	item, err := p.DB.Get(ctx, p.Tables.Supplements, Key{PK: athlete, SK: sk}, GetOptions{Consistent: true})
	if err != nil {
		return err
	}
	if item != nil {
		removeSupplementFields(program)
	}
	for _, field := range supplementFields {
		if item != nil {
			if _, ok := item[field]; ok {
				program[field] = item[field]
			}
		}
	}
	return nil
}

func (p Programs) persistSupplements(ctx context.Context, athlete, sk string, program Item) error {
	if p.Tables.Supplements == "" {
		return nil
	}
	item := Item{"pk": athlete, "sk": sk}
	for _, field := range supplementFields {
		if value, ok := program[field]; ok {
			item[field] = value
		}
	}
	if len(item) == 2 {
		return nil
	}
	return p.DB.Put(ctx, p.Tables.Supplements, item)
}

func removeSupplementFields(item Item) {
	for _, field := range supplementFields {
		delete(item, field)
	}
}

func (p Programs) saveSupplementChanges(ctx context.Context, athlete string, snapshot *Snapshot, program Item) error {
	if p.Tables.Supplements == "" {
		return nil
	}
	current, err := p.DB.Get(ctx, p.Tables.Supplements, Key{PK: athlete, SK: snapshot.SK}, GetOptions{Consistent: true})
	if err != nil {
		return err
	}
	updates := Item{}
	deleted := map[string]bool{}
	for _, field := range supplementFields {
		before, beforeOK := snapshot.Program[field]
		after, afterOK := program[field]
		if beforeOK != afterOK || !reflect.DeepEqual(before, after) {
			if afterOK {
				updates[field] = after
			} else {
				deleted[field] = true
			}
		}
	}
	if current == nil {
		return p.persistSupplements(ctx, athlete, snapshot.SK, program)
	}
	if len(updates) > 0 || len(deleted) > 0 {
		merged := pyval.CopyMap(current)
		for _, field := range supplementFields {
			if _, changed := updates[field]; changed {
				merged[field] = updates[field]
			}
			if deleted[field] {
				delete(merged, field)
			}
		}
		merged["pk"], merged["sk"] = athlete, snapshot.SK
		return p.DB.Put(ctx, p.Tables.Supplements, merged)
	}
	return nil
}
