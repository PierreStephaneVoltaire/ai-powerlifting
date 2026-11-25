package store

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"powerlifting/program/internal/env"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

const (
	defaultBlock  = "current"
	sessionPrefix = "session#"
)

type IdentityConflictError struct{ ID string }

func (e *IdentityConflictError) Error() string {
	return "Session identity " + e.ID + " occurs more than once"
}

var weekPattern = regexp.MustCompile(`(?i)W(\d+)`)

func intValue(value any, fallback int) int {
	if flag, ok := value.(bool); ok {
		if flag {
			return 1
		}
		return 0
	}
	return pyval.Int(value, fallback)
}

func ParseWeek(session map[string]any) int {
	if parsed := intValue(session["week_number"], -1); parsed >= 0 {
		return parsed
	}
	week := session["week"]
	if text, ok := week.(string); ok {
		if match := weekPattern.FindStringSubmatch(text); match != nil {
			number, _ := strconv.Atoi(match[1])
			return number
		}
	}
	return intValue(week, 0)
}

func phaseBlock(phase map[string]any) string {
	if value := pyval.Str2(phase["block"]); value != "" {
		return value
	}
	return defaultBlock
}

func ResolvePhase(session map[string]any, phases []any) map[string]any {
	week := ParseWeek(session)
	block := pyval.Str2(session["block"])
	if block == "" {
		block = defaultBlock
	}
	for _, raw := range phases {
		phase, ok := raw.(map[string]any)
		if !ok || phaseBlock(phase) != block {
			continue
		}
		if intValue(phase["start_week"], 0) <= week && week <= intValue(phase["end_week"], 0) {
			return pyval.CopyMap(phase)
		}
	}
	return map[string]any{"name": "Unscheduled", "intent": "", "start_week": int64(week), "end_week": int64(week), "block": block}
}

var internalSessionFields = []string{"pk", "sk", "entity_type", "source_pk", "source_table", "program_sk", "program_version", "program_version_number", "source_index", "same_day_ordinal", "phase_ref", "session_id"}

func PublicSession(item map[string]any, phases []any) map[string]any {
	session, _ := pyval.Sanitize(pyval.DeepCopy(item)).(map[string]any)
	if _, ok := session["session_id"]; ok {
		if _, has := session["id"]; !has {
			session["id"] = pyval.Str(session["session_id"])
		}
	}
	for _, key := range internalSessionFields {
		delete(session, key)
	}
	phase := ResolvePhase(session, phases)
	session["week_number"] = int64(ParseWeek(session))
	block := pyval.Str2(session["block"])
	if block == "" {
		block = defaultBlock
	}
	session["block"] = block
	blockID := pyval.Str2(session["block_id"])
	if blockID == "" {
		blockID = block
	}
	session["block_id"] = blockID
	session["phase"] = phase
	session["phase_name"] = nameOrUnscheduled(phase)
	return session
}

func nameOrUnscheduled(phase map[string]any) string {
	if name := pyval.Str2(phase["name"]); name != "" {
		return name
	}
	return "Unscheduled"
}

func sortKey(item map[string]any) (string, int, int, string) {
	return pyval.Str2(item["date"]), intValue(item["same_day_ordinal"], 0), intValue(item["source_index"], 0), pyval.Str2(item["sk"])
}

func sortSessionItems(items []Item) {
	sort.SliceStable(items, func(i, j int) bool {
		d1, o1, s1, k1 := sortKey(items[i])
		d2, o2, s2, k2 := sortKey(items[j])
		if d1 != d2 {
			return d1 < d2
		}
		if o1 != o2 {
			return o1 < o2
		}
		if s1 != s2 {
			return s1 < s2
		}
		return k1 < k2
	})
}

type SessionWindow struct {
	Start       string
	End         string
	BlockID     string
	ActiveBlock string
}

type Sessions struct {
	DB     DB
	Tables Tables
	Env    env.Env
}

func (s Sessions) List(ctx context.Context, athlete, programSK string, phases []any, window SessionWindow) ([]any, error) {
	prefix := sessionPrefix + programSK + "#"
	query := Query{Table: s.Tables.Sessions, PK: athlete, Consistent: true}
	if window.Start != "" || window.End != "" {
		upper := window.End
		if upper == "" {
			upper = "\U0010ffff"
		}
		bounds := [2]string{prefix + window.Start, prefix + upper + "\U0010ffff"}
		query.Between = &bounds
	} else {
		query.Prefix = prefix
	}
	items, err := s.DB.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	sortSessionItems(items)
	active := window.ActiveBlock
	if active == "" {
		active = defaultBlock
	}
	out := make([]any, 0, len(items))
	for _, item := range items {
		session := PublicSession(item, phases)
		if window.BlockID != "" && !scope.InBlock(session, window.BlockID, active) {
			continue
		}
		out = append(out, session)
	}
	return out, nil
}

func (s Sessions) buildItem(athlete, programSK string, session map[string]any, phases []any, sourceIndex, ordinal int) Item {
	now := s.Env.Stamp()
	copied := pyval.CopyMap(session)
	dateValue := pyval.Str2(copied["date"])
	if dateValue == "" {
		dateValue = "undated"
	}
	sessionID := pyval.Str2(copied["id"])
	if sessionID == "" {
		sessionID = pyval.Str2(copied["session_id"])
	}
	if sessionID == "" {
		sessionID = s.Env.UUID()
	}
	block := pyval.Str2(copied["block"])
	if block == "" {
		block = defaultBlock
	}
	blockID := pyval.Str2(copied["block_id"])
	if blockID == "" {
		blockID = block
	}
	status := pyval.Str2(copied["status"])
	if status == "" {
		status = "planned"
		if pyval.Truthy(copied["completed"]) {
			status = "completed"
		}
	}
	completed := pyval.Truthy(copied["completed"]) || status == "logged" || status == "completed"
	withBlock := pyval.CopyMap(copied)
	withBlock["block"] = block
	phase := ResolvePhase(withBlock, phases)
	planned, ok := copied["planned_exercises"].([]any)
	if !ok {
		planned = []any{}
	}
	copied["id"] = sessionID
	copied["session_id"] = sessionID
	copied["date"] = dateValue
	copied["block"] = block
	copied["block_id"] = blockID
	copied["status"] = status
	copied["completed"] = completed
	copied["week_number"] = int64(ParseWeek(copied))
	copied["phase"] = phase
	copied["phase_name"] = nameOrUnscheduled(phase)
	copied["planned_exercises"] = planned
	if exercises, ok := copied["exercises"].([]any); ok {
		for _, raw := range exercises {
			exercise, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			count := intValue(exercise["sets"], 0)
			ids, _ := exercise["set_ids"].([]any)
			setIDs := make([]any, 0, max(count, 0))
			for index := 0; index < count; index++ {
				if index < len(ids) && pyval.Truthy(ids[index]) {
					setIDs = append(setIDs, pyval.Str(ids[index]))
				} else {
					setIDs = append(setIDs, s.Env.UUID())
				}
			}
			exercise["set_ids"] = setIDs
		}
	}
	item := Item{}
	for key, value := range copied {
		item[key] = value
	}
	item["pk"] = athlete
	item["sk"] = fmt.Sprintf("%s%s#%s#%03d#%s", sessionPrefix, programSK, dateValue, ordinal, sessionID)
	item["entity_type"] = "session"
	item["source_pk"] = athlete
	item["source_table"] = string(s.Tables.Health)
	item["program_sk"] = programSK
	item["source_index"] = int64(sourceIndex)
	item["same_day_ordinal"] = int64(ordinal)
	item["phase_ref"] = phaseRef(phase)
	item["updated_at"] = now
	return item
}

func phaseRef(phase map[string]any) string {
	block := pyval.Str2(phase["block"])
	if block == "" {
		block = defaultBlock
	}
	name := pyval.Str2(phase["name"])
	if name == "" {
		name = "Unscheduled"
	}
	name = strings.ReplaceAll(name, "#", "-")
	return fmt.Sprintf("phase#%s#W%s-W%s#%s", block, pyOr(phase["start_week"], "0"), pyOr(phase["end_week"], "0"), name)
}

func pyOr(value any, fallback string) string {
	if value == nil {
		return fallback
	}
	return pyval.Str(value)
}

func ValidateIdentities(sessions []any) error {
	seen := map[string]bool{}
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		id := strings.TrimSpace(pyval.Str2(firstTruthy(session["session_id"], session["id"])))
		if id == "" {
			continue
		}
		if seen[id] {
			return &IdentityConflictError{ID: id}
		}
		seen[id] = true
	}
	return nil
}

func firstTruthy(values ...any) any {
	for _, value := range values {
		if pyval.Truthy(value) {
			return value
		}
	}
	return nil
}

var ErrSessionDate = fmt.Errorf("Every Session must have a date")

func (s Sessions) prepare(athlete, programSK string, sessions []any, phases []any) ([]Item, error) {
	ordinals := map[string]int{}
	prepared := make([]Item, 0, len(sessions))
	for index, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok || !pyval.Truthy(session["date"]) {
			return nil, ErrSessionDate
		}
		date := pyval.Str(session["date"])
		ordinals[date]++
		prepared = append(prepared, s.buildItem(athlete, programSK, session, phases, index, ordinals[date]))
	}
	asList := make([]any, len(prepared))
	for index, item := range prepared {
		asList[index] = item
	}
	if err := ValidateIdentities(asList); err != nil {
		return nil, err
	}
	return prepared, nil
}

func (s Sessions) WriteFresh(ctx context.Context, athlete, programSK string, sessions []any, phases []any) error {
	prepared, err := s.prepare(athlete, programSK, sessions, phases)
	if err != nil {
		return err
	}
	if len(prepared) == 0 {
		return nil
	}
	return s.DB.BatchPut(ctx, s.Tables.Sessions, prepared)
}

func (s Sessions) Sync(ctx context.Context, athlete, programSK string, sessions []any, phases []any) error {
	prepared, err := s.prepare(athlete, programSK, sessions, phases)
	if err != nil {
		return err
	}
	if len(prepared) > 0 {
		if err := s.DB.BatchPut(ctx, s.Tables.Sessions, prepared); err != nil {
			return err
		}
	}
	keep := make(map[string]bool, len(prepared))
	for _, item := range prepared {
		keep[pyval.Str(item["sk"])] = true
	}
	existing, err := s.DB.Query(ctx, Query{Table: s.Tables.Sessions, PK: athlete, Prefix: sessionPrefix + programSK + "#", Consistent: true})
	if err != nil {
		return err
	}
	var stale []Key
	for _, item := range existing {
		if sk := pyval.Str(item["sk"]); !keep[sk] {
			stale = append(stale, Key{PK: athlete, SK: sk})
		}
	}
	if len(stale) == 0 {
		return nil
	}
	return s.DB.BatchDelete(ctx, s.Tables.Sessions, stale)
}
