package store

import (
	"context"
	"sort"
	"strings"

	"powerlifting/program/internal/pyval"
)

const entriesIndex = "entries-by-date"

type Related struct {
	DB     DB
	Tables Tables
	Health Table
}

func (r Related) CompetitionEntries(ctx context.Context, athlete, start, end string) ([]map[string]any, error) {
	query := Query{Table: r.Tables.Competitions, Index: entriesIndex, PK: athlete, SKAttr: "entry_date"}
	switch {
	case start != "" && end != "":
		bounds := [2]string{start, end}
		query.Between = &bounds
	case start != "":
		query.AtLeast = start
	case end != "":
		query.AtMost = end
	}
	items, err := r.DB.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	return NormalizeEntries(items), nil
}

func NormalizeEntries(entries []Item) []map[string]any {
	out := make([]map[string]any, 0, len(entries))
	for _, entry := range entries {
		status := entry["user_status"]
		if !pyval.Truthy(status) {
			status = entry["status"]
		}
		if !pyval.Truthy(status) || status == "available" {
			continue
		}
		current := pyval.CopyMap(entry)
		delete(current, "pk")
		delete(current, "sk")
		delete(current, "test_seed_source_pk")
		master := entry["master_id"]
		if !pyval.Truthy(master) {
			master = strings.TrimPrefix(pyval.Str2(entry["sk"]), "COMP#")
		}
		current["master_id"] = master
		date := entry["start_date"]
		if !pyval.Truthy(date) {
			date = entry["date"]
		}
		if !pyval.Truthy(date) {
			date = nil
		}
		current["date"] = date
		current["status"] = status
		federation := entry["federation_label"]
		if !pyval.Truthy(federation) {
			federation = entry["federation"]
		}
		current["federation"] = federation
		current["body_weight_kg"] = entry["body_weight_kg"]
		if pyval.Truthy(entry["units"]) {
			current["units"] = entry["units"]
		} else {
			current["units"] = "kg"
		}
		out = append(out, current)
	}
	sort.SliceStable(out, func(i, j int) bool {
		di, dj := pyval.Str2(out[i]["date"]), pyval.Str2(out[j]["date"])
		if di != dj {
			return di < dj
		}
		return pyval.Str2(out[i]["master_id"]) < pyval.Str2(out[j]["master_id"])
	})
	return out
}

func (r Related) Template(ctx context.Context, library, sk string) (Item, error) {
	return r.DB.Get(ctx, r.Tables.Templates, Key{PK: library, SK: sk}, GetOptions{})
}

func (r Related) Versioned(ctx context.Context, athlete, sk string) (Item, error) {
	return r.DB.Get(ctx, r.Tables.Health, Key{PK: athlete, SK: sk}, GetOptions{})
}

func (r Related) CompetitionItems(ctx context.Context, athlete string) ([]Item, error) {
	return r.DB.Query(ctx, Query{Table: r.Tables.Competitions, Index: entriesIndex, PK: athlete, SKAttr: "entry_date"})
}
