package session

import (
	"context"
	"slices"
	"strings"
	"time"

	"powerlifting/sessions/internal/apperr"
	"powerlifting/sessions/internal/value"
)

type Service struct {
	Sessions    Sessions
	Programs    Programs
	SourceTable string
	Now         func() time.Time
	NewID       func() string
}

type Scope struct {
	ProgramSK string
	Phases    []any
}

type Selector struct {
	Date      string
	Index     *int
	SessionID string
}

func (s *Service) Resolve(ctx context.Context, pk string) (Scope, error) {
	programSK, err := s.Programs.CurrentSK(ctx, pk)
	if err != nil {
		return Scope{}, err
	}
	if programSK == "" {
		return Scope{}, apperr.NotFound("Program not found")
	}
	program, err := s.Programs.Program(ctx, pk, programSK)
	if err != nil {
		return Scope{}, err
	}
	phases := program.Phases
	if phases == nil {
		phases = []any{}
	}
	return Scope{ProgramSK: programSK, Phases: phases}, nil
}

func (s *Service) load(ctx context.Context, pk, programSK string) ([]value.Item, error) {
	items, err := s.Sessions.ForProgram(ctx, pk, programSK)
	if err != nil {
		return nil, err
	}
	sortItems(items)
	return items, nil
}

func find(items []value.Item, sel Selector) (value.Item, error) {
	if sel.SessionID != "" {
		var matches []value.Item
		for _, item := range items {
			if rawIdentity(item) == sel.SessionID {
				matches = append(matches, item)
			}
		}
		switch len(matches) {
		case 1:
			return matches[0], nil
		case 0:
			return nil, apperr.Validation("Session " + sel.SessionID + " no longer exists")
		}
		return nil, apperr.Validation("Session identity " + sel.SessionID + " is ambiguous")
	}
	var dated []value.Item
	for _, item := range items {
		if value.Str(value.Or(item["date"], "")) == sel.Date {
			dated = append(dated, item)
		}
	}
	if sel.Index != nil {
		if *sel.Index < 0 || *sel.Index >= len(dated) {
			return nil, apperr.Validation("Session at index " + itoa(*sel.Index) + " not found")
		}
		return dated[*sel.Index], nil
	}
	switch len(dated) {
	case 1:
		return dated[0], nil
	case 0:
		return nil, apperr.Validation("Session not found with date=" + sel.Date)
	}
	return nil, apperr.Validation("Several Sessions are on " + sel.Date + "; choose one by id")
}

func itoa(n int) string { return string(value.Int(n)) }

func (s *Service) Get(ctx context.Context, pk string, scope Scope, sel Selector) (value.Item, error) {
	items, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	item, err := find(items, sel)
	if err != nil {
		return nil, err
	}
	return public(item, scope.Phases), nil
}

func (s *Service) ListFull(ctx context.Context, pk string, scope Scope) ([]any, error) {
	items, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	out := make([]any, len(items))
	for i, item := range items {
		out[i] = public(item, scope.Phases)
	}
	return out, nil
}

func (s *Service) Create(ctx context.Context, pk string, scope Scope, session value.Item) (value.Item, error) {
	if !value.Truthy(session["date"]) {
		return nil, apperr.Validation("Session date is required")
	}
	existing, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	item := s.build(pk, draft{programSK: scope.ProgramSK, session: session, phases: scope.Phases, sourceIdx: len(existing), siblings: existing})
	id := identity(item)
	if id != "" && slices.ContainsFunc(existing, func(candidate value.Item) bool { return identity(candidate) == id }) {
		return nil, apperr.IdentityConflict("Session identity " + id + " already exists")
	}
	if err := s.Sessions.Put(ctx, item); err != nil {
		return nil, err
	}
	return withPhase(item, scope.Phases), nil
}

func (s *Service) Patch(ctx context.Context, pk string, scope Scope, sel Selector, patch value.Item) (value.Item, error) {
	items, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	existing, err := find(items, sel)
	if err != nil {
		return nil, err
	}
	for _, key := range []string{"id", "session_id"} {
		if supplied, present := patch[key]; present && value.Str(supplied) != value.Str(existing["session_id"]) {
			return nil, apperr.Validation("Session identity cannot be changed")
		}
	}
	session := public(existing, scope.Phases)
	for key, v := range value.CopyItem(patch) {
		session[key] = v
	}
	item := s.build(pk, draft{programSK: scope.ProgramSK, session: session, phases: scope.Phases, existing: existing, siblings: items})
	delete(item, "media_revision")
	if item["sk"] != existing["sk"] {
		if err := s.Sessions.Delete(ctx, pk, value.Str(existing["sk"])); err != nil {
			return nil, err
		}
	}
	if err := s.Sessions.Put(ctx, item); err != nil {
		return nil, err
	}
	return withPhase(item, scope.Phases), nil
}

func (s *Service) Delete(ctx context.Context, pk string, scope Scope, sel Selector) (value.Item, error) {
	items, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	existing, err := find(items, sel)
	if err != nil {
		return nil, err
	}
	if err := s.Sessions.Delete(ctx, pk, value.Str(existing["sk"])); err != nil {
		return nil, err
	}
	return value.Item{"deleted": sel.Date}, nil
}

func ensureUnique(items []value.Item) error {
	seen := map[string]bool{}
	for _, item := range items {
		id := identity(item)
		if id == "" {
			continue
		}
		if seen[id] {
			return apperr.IdentityConflict("Session identity " + id + " occurs more than once")
		}
		seen[id] = true
	}
	return nil
}

func (s *Service) ReplaceAll(ctx context.Context, pk string, scope Scope, sessions []any) error {
	existing, err := s.load(ctx, pk, scope.ProgramSK)
	if err != nil {
		return err
	}
	if err := ensureUnique(existing); err != nil {
		return err
	}
	ordinals := map[string]int{}
	prepared := make([]value.Item, 0, len(sessions))
	for position, entry := range sessions {
		session, ok := value.Map(entry)
		if !ok || !value.Truthy(session["date"]) {
			return apperr.Validation("Every Session must have a date")
		}
		date := value.Str(session["date"])
		ordinals[date]++
		ordinal := ordinals[date]
		var sameDay []value.Item
		for _, item := range existing {
			if item["date"] == date {
				sameDay = append(sameDay, item)
			}
		}
		var previous value.Item
		if value.Truthy(session["id"]) {
			for _, item := range existing {
				if item["session_id"] == session["id"] {
					previous = item
					break
				}
			}
		}
		if previous == nil && len(sameDay) >= ordinal {
			previous = sameDay[ordinal-1]
		}
		prepared = append(prepared, s.build(pk, draft{programSK: scope.ProgramSK, session: session, phases: scope.Phases, existing: previous, sourceIdx: position, sameDay: ordinal}))
	}
	if err := ensureUnique(prepared); err != nil {
		return err
	}
	kept := map[string]bool{}
	for _, item := range prepared {
		kept[value.Str(item["sk"])] = true
	}
	var deletes []string
	for _, item := range existing {
		if sk := value.Str(item["sk"]); !kept[sk] {
			deletes = append(deletes, sk)
		}
	}
	return s.Sessions.Apply(ctx, pk, deletes, prepared)
}

func (s *Service) List(ctx context.Context, pk string, limit int) (value.Item, error) {
	scope, err := s.Resolve(ctx, pk)
	if err != nil {
		return nil, err
	}
	all, err := s.Sessions.Listing(ctx, pk, scope.ProgramSK)
	if err != nil {
		return nil, err
	}
	var rows []value.Item
	for _, raw := range all {
		item := value.Sanitize(raw).(map[string]any)
		exercises, _ := item["exercises"].([]any)
		sessionID := value.Or(item["session_id"], item["id"])
		rows = append(rows, value.Item{
			"id":               nilIfFalsy(sessionID),
			"session_id":       nilIfFalsy(sessionID),
			"sk":               item["sk"],
			"date":             value.Or(item["date"], ""),
			"week_number":      value.Int(value.IntOf(item["week_number"], 0)),
			"block":            value.Or(defaulted(item, "block", defaultBlock), defaultBlock),
			"label":            defaulted(item, "label", ""),
			"name":             defaulted(item, "name", ""),
			"status":           defaulted(item, "status", ""),
			"completed":        value.Truthy(item["completed"]),
			"exercise_count":   value.Int(len(exercises)),
			"same_day_ordinal": value.Int(value.IntOf(item["same_day_ordinal"], 0)),
		})
	}
	slices.SortStableFunc(rows, func(a, b value.Item) int {
		return -compareSummary(a, b)
	})
	page := rows
	if len(page) > limit {
		page = page[:limit]
	}
	list := make([]any, len(page))
	for i, row := range page {
		list[i] = row
	}
	return value.Item{"sessions": list, "count": value.Int(len(page)), "total": value.Int(len(rows))}, nil
}

func compareSummary(a, b value.Item) int {
	if c := strings.Compare(value.Str(a["date"]), value.Str(b["date"])); c != 0 {
		return c
	}
	if x, y := value.IntOf(a["same_day_ordinal"], 0), value.IntOf(b["same_day_ordinal"], 0); x != y {
		if x < y {
			return -1
		}
		return 1
	}
	return strings.Compare(value.Str(a["sk"]), value.Str(b["sk"]))
}

func defaulted(item value.Item, key string, fallback any) any {
	if v, present := item[key]; present {
		return v
	}
	return fallback
}

func nilIfFalsy(v any) any {
	if value.Truthy(v) {
		return v
	}
	return nil
}

func (s *Service) Range(ctx context.Context, pk, start, end string) ([]any, error) {
	programSK, err := s.Programs.CurrentSK(ctx, pk)
	if err != nil {
		return nil, err
	}
	if programSK == "" {
		return nil, apperr.NotFound("Program not found")
	}
	program, err := s.Programs.Program(ctx, pk, programSK)
	if err != nil {
		return nil, err
	}
	if !program.Found {
		return nil, apperr.NotFound("Program item not found at %s", programSK)
	}
	phases := program.Phases
	if phases == nil {
		phases = []any{}
	}
	items, err := s.load(ctx, pk, programSK)
	if err != nil {
		return nil, err
	}
	var rows []value.Item
	for _, item := range items {
		session := public(item, phases)
		date := value.Str(value.Or(session["date"], ""))
		if date < start || date > end {
			continue
		}
		session["phase"] = rangePhase(session, phases)
		rows = append(rows, session)
	}
	slices.SortStableFunc(rows, func(a, b value.Item) int {
		return strings.Compare(value.Str(value.Or(a["date"], "")), value.Str(value.Or(b["date"], "")))
	})
	out := make([]any, len(rows))
	for i, row := range rows {
		out[i] = row
	}
	return out, nil
}

func rangePhase(session value.Item, phases []any) any {
	week := value.Rat(session["week_number"], 1)
	for _, candidate := range phases {
		phase, ok := value.Map(candidate)
		if !ok {
			continue
		}
		if value.Rat(phase["start_week"], 0).Cmp(week) <= 0 && week.Cmp(value.Rat(defaulted(phase, "end_week", value.Int(99)), 99)) <= 0 {
			return value.Copy(phase)
		}
	}
	if len(phases) > 0 {
		return value.Copy(phases[0])
	}
	return value.Item{}
}
