package views

import (
	"cmp"
	"context"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

const (
	pointerSK    = "program#current"
	defaultBlock = "current"
	unscheduled  = "Unscheduled"
)

var weekPattern = regexp.MustCompile(`(?i)W(\d+)`)

var internalFields = []string{
	"pk", "sk", "entity_type", "source_pk", "source_table", "program_sk", "program_version",
	"program_version_number", "source_index", "same_day_ordinal", "phase_ref", "session_id",
}

type Program struct {
	SK   string
	Item map[string]any
}

func (v *Views) ProgramSK(ctx context.Context, athlete string) (string, error) {
	pointer, err := v.DB.Get(ctx, v.DB.Tables.Health, store.PKSK(athlete, pointerSK))
	if err != nil || pointer == nil {
		return "", err
	}
	return value.Str(value.Or(pointer["ref_sk"], "")), nil
}

func (v *Views) CurrentProgram(ctx context.Context, athlete string) (string, map[string]any, error) {
	sk, err := v.ProgramSK(ctx, athlete)
	if err != nil || sk == "" {
		return sk, nil, err
	}
	item, err := v.DB.Get(ctx, v.DB.Tables.Health, store.PKSK(athlete, sk))
	if err != nil || item == nil {
		return sk, nil, err
	}
	return sk, value.Sanitize(item).(map[string]any), nil
}

func intOf(v any, fallback int) int { return value.IntOf(v, fallback) }

func weekNumber(session map[string]any) int {
	if parsed := intOf(session["week_number"], -1); parsed >= 0 {
		return parsed
	}
	week := session["week"]
	if text, ok := week.(string); ok {
		if match := weekPattern.FindStringSubmatch(text); match != nil {
			if n, err := strconv.Atoi(match[1]); err == nil {
				return n
			}
		}
	}
	return intOf(week, 0)
}

func blockOf(record map[string]any) string {
	return value.Str(value.Or(record["block"], defaultBlock))
}

func resolvePhase(session map[string]any, phases []any) map[string]any {
	week := weekNumber(session)
	block := blockOf(session)
	for _, candidate := range phases {
		phase, ok := candidate.(map[string]any)
		if !ok || blockOf(phase) != block {
			continue
		}
		if intOf(phase["start_week"], 0) <= week && week <= intOf(phase["end_week"], 0) {
			return value.Copy(phase).(map[string]any)
		}
	}
	return map[string]any{"name": unscheduled, "intent": "", "start_week": value.Int(week), "end_week": value.Int(week), "block": block}
}

func publicSession(item value.Item, phases []any) map[string]any {
	session := value.Sanitize(item).(map[string]any)
	if id, present := session["session_id"]; present {
		if _, hasID := session["id"]; !hasID {
			session["id"] = value.Str(id)
		}
	}
	for _, key := range internalFields {
		delete(session, key)
	}
	phase := resolvePhase(session, phases)
	session["week_number"] = value.Int(weekNumber(session))
	session["block"] = blockOf(session)
	session["block_id"] = value.Str(value.Or(session["block_id"], session["block"]))
	session["phase"] = phase
	session["phase_name"] = value.Str(value.Or(phase["name"], unscheduled))
	return session
}

func (v *Views) Sessions(ctx context.Context, athlete, programSK string, phases []any) ([]map[string]any, error) {
	rows, err := v.DB.Query(ctx, store.Query{
		Table:      v.DB.Tables.Sessions,
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": athlete, ":prefix": "session#" + programSK + "#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	slices.SortStableFunc(rows, func(a, b value.Item) int {
		return cmp.Or(
			strings.Compare(value.Str(value.Or(a["date"], "")), value.Str(value.Or(b["date"], ""))),
			cmp.Compare(intOf(a["same_day_ordinal"], 0), intOf(b["same_day_ordinal"], 0)),
			cmp.Compare(intOf(a["source_index"], 0), intOf(b["source_index"], 0)),
			strings.Compare(value.Str(value.Or(a["sk"], "")), value.Str(value.Or(b["sk"], ""))),
		)
	})
	if phases == nil {
		phases = []any{}
	}
	sessions := make([]map[string]any, len(rows))
	for i, row := range rows {
		sessions[i] = publicSession(row, phases)
	}
	return sessions, nil
}
