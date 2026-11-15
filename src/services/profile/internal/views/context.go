package views

import (
	"context"
	"regexp"
	"sort"
	"strings"
	"time"

	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var servedMediaPath = regexp.MustCompile(`^/api/(?:budget|profiles|videos)/media/`)

type Analytics interface {
	EstimatedMaxes(ctx context.Context, person, athlete string) map[string]any
}

func (v *Views) ResolveAvatar(ctx context.Context, athlete, person, key string) (map[string]any, error) {
	missing := apperr.New(404, "not_found", "Avatar not found")
	owner, err := v.People.Record(ctx, athlete)
	if err != nil {
		return nil, err
	}
	stored := ""
	if owner != nil {
		if url, ok := owner["avatar_url"].(string); ok {
			stored = servedMediaPath.ReplaceAllString(url, "")
		}
	}
	if owner == nil || stored != key || !strings.HasPrefix(key, "profiles/") {
		return nil, missing
	}
	granted, err := v.Access.Context(ctx, person, athleteOf(owner))
	if err != nil {
		return nil, err
	}
	if !granted.Has("profile:read") {
		return nil, missing
	}
	return map[string]any{"s3_key": key}, nil
}

var metaFields = []struct {
	Domain string
	Fields []string
}{
	{"competition", []string{"practicing_for", "weight_class_kg", "weight_class_confirm_by", "attempt_pct", "lift_attempt_settings"}},
	{"weight-log", []string{"current_body_weight_kg", "current_body_weight_lb", "height_cm", "arm_wingspan_cm", "leg_length_cm", "body_fat_range"}},
	{"performance", []string{"target_squat_kg", "target_bench_kg", "target_dl_kg", "target_total_kg", "manual_maxes"}},
	{"federation", []string{"federation"}},
}

func filteredMeta(meta map[string]any, granted *access.Context) map[string]any {
	out := value.Copy(meta).(map[string]any)
	if !granted.Has("program:read") {
		allowed := map[string]bool{}
		for _, group := range metaFields {
			if granted.Has(group.Domain + ":read") {
				for _, name := range group.Fields {
					allowed[name] = true
				}
			}
		}
		for name := range out {
			if !allowed[name] {
				delete(out, name)
			}
		}
	}
	for _, group := range metaFields {
		if !granted.Has(group.Domain + ":read") {
			for _, name := range group.Fields {
				delete(out, name)
			}
		}
	}
	if !granted.Has("performance:read") {
		for _, entry := range asList(out["blocks"]) {
			if block, ok := entry.(map[string]any); ok {
				delete(block, "start_maxes_kg")
			}
		}
	}
	return out
}

func (v *Views) loadProgram(ctx context.Context, athlete string) (map[string]any, error) {
	health := v.DB.Tables.Health
	var sk string
	pointer, err := v.DB.Get(ctx, health, store.PKSK(athlete, pointerSK))
	if err != nil {
		return nil, err
	}
	if pointer != nil {
		sk = value.Str(value.Or(pointer["ref_sk"], ""))
	} else {
		rows, err := v.DB.Query(ctx, store.Query{
			Table:   health,
			KeyCond: "pk = :pk AND begins_with(sk, :prefix)",
			Values:  map[string]any{":pk": athlete, ":prefix": "program#v"},
		})
		if err != nil {
			return nil, err
		}
		latest := -1
		for _, row := range rows {
			if published, ok := row["published"].(bool); ok && !published {
				continue
			}
			name := strings.TrimPrefix(value.Str(row["sk"]), "program#v")
			name, _, _ = strings.Cut(name, "-")
			version := value.IntOf(name, -1)
			if version > latest {
				latest, sk = version, value.Str(row["sk"])
			}
		}
	}
	if sk == "" {
		return nil, nil
	}
	item, err := v.DB.Get(ctx, health, store.PKSK(athlete, sk))
	if err != nil {
		return nil, err
	}
	if item == nil {
		return nil, apperr.Internal("Program item not found at " + sk)
	}
	if published, ok := item["published"].(bool); ok && !published {
		return nil, nil
	}
	program := value.Sanitize(item).(map[string]any)
	delete(program, "pk")
	delete(program, "sk")
	if _, ok := program["meta"].(map[string]any); !ok {
		program["meta"] = map[string]any{}
	}
	phases := asList(program["phases"])
	sessions, err := v.Sessions(ctx, athlete, sk, phases)
	if err != nil {
		return nil, err
	}
	list := make([]any, len(sessions))
	for i, session := range sessions {
		list[i] = session
	}
	program["sessions"] = list
	return program, nil
}

func (v *Views) HandlerContext(ctx context.Context, athlete, person string, granted *access.Context, analytics Analytics) (map[string]any, error) {
	owner, err := v.People.Record(ctx, athlete)
	if err != nil {
		return nil, err
	}
	var profile map[string]any
	if owner != nil {
		vocabulary, err := v.Tags.Load(ctx)
		if err != nil {
			return nil, err
		}
		if profile, err = v.Visible(ctx, owner, person, vocabulary, true); err != nil {
			return nil, err
		}
	}
	if profile == nil {
		return nil, apperr.New(404, "not_found", "Athlete not found")
	}
	entries, err := v.DB.Query(ctx, store.Query{
		Table:      v.DB.Tables.Competitions,
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": athlete, ":prefix": "COMP#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	visible := entries[:0:0]
	for _, entry := range entries {
		if granted.ReadScope.Unrestricted || access.EntryMatches(entry, granted.ReadScope) {
			visible = append(visible, entry)
		}
	}
	program, err := v.loadProgram(ctx, athlete)
	if err != nil {
		return nil, err
	}
	meta := map[string]any{}
	var sessionList []map[string]any
	if program != nil {
		meta = filteredMeta(asMap(program["meta"]), granted)
		for _, entry := range asList(program["sessions"]) {
			session := asMap(entry)
			if value.Str(value.Or(session["block"], defaultBlock)) == defaultBlock {
				sessionList = append(sessionList, session)
			}
		}
	}
	currentID := meta["current_block_id"]
	var block any
	for _, entry := range asList(meta["blocks"]) {
		if candidate, ok := entry.(map[string]any); ok && candidate["id"] == currentID {
			block = candidate
			break
		}
	}
	if block == nil {
		block = map[string]any{"id": value.Or(currentID, defaultBlock), "name": "Current Block", "status": "active"}
	}
	sort.SliceStable(sessionList, func(i, j int) bool {
		return value.Str(value.Or(sessionList[i]["date"], "")) < value.Str(value.Or(sessionList[j]["date"], ""))
	})
	today := v.Env.Now().UTC().Format("2006-01-02")
	var phase any
	if granted.Has("sessions:read") {
		phase = sessionDerivedPhase(sessionList, today)
	} else if program != nil {
		phase = scheduledPhase(asList(program["phases"]), meta, block, today)
	}
	estimated := map[string]any{}
	if granted.Has("performance:read") && analytics != nil {
		if maxes := analytics.EstimatedMaxes(ctx, person, athlete); maxes != nil {
			estimated = maxes
		}
	}
	programRead := granted.Has("program:read")
	result := map[string]any{"profile": profile, "block": nil, "phase": nil, "estimated_maxes": estimated, "competitions": []any{}, "notes": []any{}}
	if programRead {
		result["block"], result["phase"] = block, phase
		if notes, ok := meta["block_notes"].([]any); ok {
			result["notes"] = notes
		}
	}
	if granted.Has("competition:read") {
		competitions := []any{}
		for _, entry := range visible {
			trimmed := map[string]any{}
			for key, v := range entry {
				if key != "pk" && key != "test_seed_source_pk" {
					trimmed[key] = v
				}
			}
			competitions = append(competitions, trimmed)
		}
		result["competitions"] = competitions
	}
	return value.Sanitize(result).(map[string]any), nil
}

func sessionDerivedPhase(sessionList []map[string]any, today string) any {
	if len(sessionList) == 0 {
		return nil
	}
	nearest := sessionList[len(sessionList)-1]
	for _, session := range sessionList {
		if value.Str(value.Or(session["date"], "")) >= today {
			nearest = session
			break
		}
	}
	return nearest["phase"]
}

var weekdayIndex = map[string]int{"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}

func scheduledPhase(phases []any, meta map[string]any, block any, today string) any {
	start, err := time.Parse("2006-01-02", value.Str(value.Or(meta["program_start"], "")))
	if err != nil {
		return nil
	}
	now, err := time.Parse("2006-01-02", today)
	if err != nil {
		return nil
	}
	weekStartDay := 0
	if record, ok := block.(map[string]any); ok {
		if index, known := weekdayIndex[value.Str(value.Or(record["week_start_day"], ""))]; known {
			weekStartDay = index
		}
	}
	offset := (int(start.Weekday())+6)%7 - weekStartDay
	anchor := start.AddDate(0, 0, -((offset + 7) % 7))
	week := max(1, int(now.Sub(anchor).Hours()/24)/7+1)
	return resolvePhase(map[string]any{"week_number": value.Int(week), "block": defaultBlock}, phases)
}
