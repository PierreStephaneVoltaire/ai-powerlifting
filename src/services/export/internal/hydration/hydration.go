package hydration

import (
	"context"
	"errors"
	"sort"
	"strings"

	"powerlifting/export/internal/publication"
	"powerlifting/export/internal/scope"
	"powerlifting/export/internal/values"
)

type Reader interface {
	Get(context.Context, string, string, string) (map[string]any, error)
	Query(context.Context, string, string, string) ([]map[string]any, error)
	Competitions(context.Context, string, string, string) ([]map[string]any, error)
}

type Tables struct{ Health, Sessions, Supplements string }
type Loaded struct {
	Program   map[string]any
	ProgramSK string
}
type Loader struct {
	Reader Reader
	Tables Tables
}

func (l Loader) Load(ctx context.Context, athlete, block, start, end string, access map[string]any) (*Loaded, error) {
	if athlete == "" {
		return nil, errors.New("athlete scope required")
	}
	pointer, err := l.Reader.Get(ctx, l.Tables.Health, athlete, "program#current")
	if err != nil {
		return nil, err
	}
	sk := values.Str2(pointer["ref_sk"])
	if sk == "" {
		return nil, errors.New("program not found")
	}
	stored, err := l.Reader.Get(ctx, l.Tables.Health, athlete, sk)
	if err != nil {
		return nil, err
	}
	if stored == nil {
		return nil, errors.New("program not found")
	}
	program := values.CopyMap(stored)
	delete(program, "pk")
	delete(program, "sk")
	supplements, err := l.Reader.Get(ctx, l.Tables.Supplements, athlete, sk)
	if err != nil {
		return nil, err
	}
	if supplements != nil {
		delete(program, "supplements")
		delete(program, "supplement_phases")
		for _, key := range []string{"supplements", "supplement_phases"} {
			if value, ok := supplements[key]; ok {
				program[key] = value
			}
		}
	}
	phases, _ := program["phases"].([]any)
	items, err := l.Reader.Query(ctx, l.Tables.Sessions, athlete, "session#"+sk+"#")
	if err != nil {
		return nil, err
	}
	sortSessionItems(items)
	sessions := make([]any, 0, len(items))
	for _, item := range items {
		session := PublicSession(item, phases)
		date := values.Str2(session["date"])
		if len(date) > 10 {
			date = date[:10]
		}
		if start != "" && date < start || end != "" && date > end {
			continue
		}
		sessions = append(sessions, session)
	}
	program["sessions"] = sessions
	entries, err := l.Reader.Competitions(ctx, athlete, start, end)
	if err != nil {
		return nil, err
	}
	program["competitions"] = normalizedEntries(entries)
	if block != scope.AllBlocks {
		program = scope.Program(program, block)
	}
	if access != nil {
		program = publication.ProgramView(program, publication.Access(access))
	}
	return &Loaded{Program: program, ProgramSK: sk}, nil
}

func normalizedEntries(entries []map[string]any) []any {
	result := []any{}
	for _, entry := range entries {
		status := entry["user_status"]
		if !values.Truthy(status) {
			status = entry["status"]
		}
		if !values.Truthy(status) || status == "available" {
			continue
		}
		current := values.CopyMap(entry)
		delete(current, "pk")
		delete(current, "sk")
		delete(current, "test_seed_source_pk")
		master := entry["master_id"]
		if !values.Truthy(master) {
			master = strings.TrimPrefix(values.Str2(entry["sk"]), "COMP#")
		}
		current["master_id"] = master
		date := entry["start_date"]
		if !values.Truthy(date) {
			date = entry["date"]
		}
		if !values.Truthy(date) {
			date = nil
		}
		current["date"] = date
		current["status"] = status
		federation := entry["federation_label"]
		if !values.Truthy(federation) {
			federation = entry["federation"]
		}
		current["federation"] = federation
		current["body_weight_kg"] = entry["body_weight_kg"]
		if !values.Truthy(entry["units"]) {
			current["units"] = "kg"
		}
		result = append(result, current)
	}
	sort.SliceStable(result, func(i, j int) bool {
		a := result[i].(map[string]any)
		b := result[j].(map[string]any)
		if values.Str2(a["date"]) != values.Str2(b["date"]) {
			return values.Str2(a["date"]) < values.Str2(b["date"])
		}
		return values.Str2(a["master_id"]) < values.Str2(b["master_id"])
	})
	return result
}
