package entries

import (
	"context"
	"sort"
	"strings"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/pyval"
	"powerlifting/competition/internal/store"
)

var mutableFields = map[string]bool{
	"units": true, "user_status": true, "weight_class_kg": true, "body_weight_kg": true,
	"targets": true, "results": true, "post_meet_report": true, "hotel_required": true,
	"counts_toward_federation_ids": true, "between_comp_plan": true, "comp_day_protocol": true,
	"decision_date": true, "attempt_selection": true, "projected_at_t_minus_1w": true,
	"projection_snapshot_date": true, "notes": true,
}

type Service struct {
	Entries  store.Entries
	Programs store.Programs
	Now      func() time.Time
}

func FormatTimestamp(moment time.Time) string {
	moment = moment.UTC()
	layout := "2006-01-02T15:04:05"
	if moment.Nanosecond()/1000 != 0 {
		layout += ".000000"
	}
	return moment.Format(layout) + "+00:00"
}

func validation(message string) error { return apperr.Validation(message) }

func normaliseUnits(item map[string]any) {
	if units := item["units"]; units != "kg" && units != "lb" {
		item["units"] = "kg"
	}
}

func isDirectoryEntry(entry map[string]any) bool {
	return pyval.Or(entry["user_status"], entry["status"], "available") == "available"
}

func participationDate(entry map[string]any) (string, bool) {
	if isDirectoryEntry(entry) {
		return "", false
	}
	date := pyval.Or(entry["start_date"], entry["date"])
	if !pyval.Truthy(date) {
		return "", false
	}
	return pyval.Str(date), true
}

func overlay(base, top map[string]any) map[string]any {
	merged := make(map[string]any, len(base)+len(top))
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range top {
		merged[key] = value
	}
	return merged
}

func (s Service) List(ctx context.Context, pk string, args map[string]any) ([]any, error) {
	country := countryCode(args["country"])
	state := ""
	if pyval.Truthy(args["state"]) {
		state = strings.ToLower(strings.TrimSpace(pyval.Str(args["state"])))
	}
	raws, err := s.Entries.Query(ctx, pk, store.EntrySKPrefix)
	if err != nil {
		return nil, err
	}
	var items []map[string]any
	for _, raw := range raws {
		competition := map[string]any(raw)
		delete(competition, "pk")
		sk := ""
		if value, ok := competition["sk"].(string); ok {
			sk = value
		}
		delete(competition, "sk")
		if !pyval.Truthy(competition["master_id"]) {
			if id := strings.TrimPrefix(sk, store.EntrySKPrefix); id != "" {
				competition["master_id"] = id
			} else {
				competition["master_id"] = nil
			}
		}
		normaliseUnits(competition)
		if country != "" && countryCode(competition["venue_country"]) != country {
			continue
		}
		if state != "" && strings.ToLower(strings.TrimSpace(textOf(competition["venue_state"]))) != state {
			continue
		}
		items = append(items, competition)
	}
	if block := args["block_id"]; pyval.Truthy(block) {
		active, err := ActiveBlockID(ctx, s.Programs, pk)
		if err != nil {
			return nil, err
		}
		filtered := items[:0]
		for _, competition := range items {
			if isDirectoryEntry(competition) || inBlock(competition, pyval.Str(block), active) {
				filtered = append(filtered, competition)
			}
		}
		items = filtered
	}
	sort.SliceStable(items, func(i, j int) bool { return textOf(items[i]["start_date"]) < textOf(items[j]["start_date"]) })
	out := make([]any, len(items))
	for index, item := range items {
		out[index] = item
	}
	return out, nil
}

func textOf(value any) string {
	if pyval.Truthy(value) {
		return pyval.Str(value)
	}
	return ""
}

func (s Service) Update(ctx context.Context, pk string, args map[string]any) (map[string]any, error) {
	masterID := textOf(args["master_id"])
	if masterID == "" {
		return nil, validation("master_id is required")
	}
	patch, ok := args["patch"].(map[string]any)
	if !ok {
		return nil, validation("patch must be an object")
	}
	var unknown []string
	for field := range patch {
		if !mutableFields[field] {
			unknown = append(unknown, field)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return nil, validation("competition fields are not editable: " + strings.Join(unknown, ", "))
	}
	if units, present := patch["units"]; present && units != "kg" && units != "lb" {
		return nil, validation("competition.units must be kg or lb")
	}

	sk := store.EntrySKPrefix + masterID
	current, err := s.Entries.Get(ctx, pk, sk)
	if err != nil {
		return nil, err
	}
	if len(current) == 0 {
		return nil, validation("Competition not found: " + masterID)
	}
	normaliseUnits(current)

	applied := pyval.Copy(patch).(map[string]any)
	if !pyval.Truthy(current["block_id"]) && !isDirectoryEntry(overlay(current, applied)) {
		if !pyval.Truthy(applied["block_id"]) {
			active, err := ActiveBlockID(ctx, s.Programs, pk)
			if err != nil {
				return nil, err
			}
			applied["block_id"] = active
		}
	}
	var removed []string
	entryDate, indexed := participationDate(overlay(current, applied))
	if indexed && current["entry_date"] != entryDate {
		applied["entry_date"] = entryDate
	}
	if !indexed && pyval.Truthy(current["entry_date"]) {
		removed = []string{"entry_date"}
	}
	if report, present := applied["post_meet_report"]; present {
		stored, _ := current["post_meet_report"].(map[string]any)
		switch {
		case report == nil && stored != nil && pyval.Truthy(stored["attempts"]):
			applied["post_meet_report"] = pyval.Copy(stored)
		case report != nil:
			normalised, err := normaliseReport(masterID, report, current["post_meet_report"])
			if err != nil {
				return nil, validation(err.Error())
			}
			applied["post_meet_report"] = normalised
		}
	}

	now := FormatTimestamp(s.Now())
	result := map[string]any{}
	for key, value := range current {
		result[key] = value
	}
	for _, field := range removed {
		delete(result, field)
	}
	for key, value := range applied {
		result[key] = pyval.Copy(value)
	}
	result["updated_at"] = now
	delete(result, "pk")
	delete(result, "sk")

	names := make([]string, 0, len(applied))
	for name := range applied {
		names = append(names, name)
	}
	sort.Strings(names)
	update := store.EntryUpdate{UpdatedAt: now, Remove: removed}
	for _, name := range names {
		update.Set = append(update.Set, store.Field{Name: name, Value: applied[name]})
	}
	if err := s.Entries.Update(ctx, pk, sk, update); err != nil {
		return nil, err
	}
	return result, nil
}

func (s Service) Complete(ctx context.Context, pk string, args map[string]any) (map[string]any, error) {
	if textOf(args["master_id"]) == "" {
		return nil, validation("master_id is required")
	}
	patch := map[string]any{
		"user_status":    "completed",
		"body_weight_kg": args["body_weight_kg"],
		"results":        args["results"],
	}
	if args["post_meet_report"] != nil {
		patch["post_meet_report"] = args["post_meet_report"]
	}
	return s.Update(ctx, pk, map[string]any{"master_id": args["master_id"], "patch": patch})
}
