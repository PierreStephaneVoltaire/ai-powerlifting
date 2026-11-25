package ops

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"sort"
	"strings"
	"time"
	"unicode/utf8"

	"powerlifting/program/internal/markdown"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

var perSetFields = map[string]bool{"sets_data": true, "set_ids": true, "set_statuses": true, "failed_set_reasons": true}

func valueKey(value any) string {
	if pyval.IsNumber(value) {
		number, _ := pyval.Float(value)
		return fmt.Sprintf("n:%v", number)
	}
	return fmt.Sprintf("%T:%s", value, pyval.Str(value))
}

func at(values any, index int) any {
	list, ok := values.([]any)
	if ok && index < len(list) {
		return list[index]
	}
	return nil
}

func expandPerformedSets(exercise map[string]any) []map[string]any {
	setsData, ok := exercise["sets_data"].([]any)
	hasDict := false
	for _, item := range setsData {
		if _, isMap := item.(map[string]any); isMap {
			hasDict = true
		}
	}
	if !ok || !hasDict {
		return []map[string]any{exercise}
	}
	type triple struct{ reps, kg, rpe any }
	values := make([]triple, len(setsData))
	statuses := make([]any, len(setsData))
	reasons := make([]any, len(setsData))
	failures := false
	uniqueValues, uniqueStatuses := map[string]bool{}, map[string]bool{}
	for index, raw := range setsData {
		item, _ := raw.(map[string]any)
		pick := func(key string) any {
			if value, present := item[key]; present {
				return value
			}
			return exercise[key]
		}
		values[index] = triple{pick("reps"), pick("kg"), pick("rpe")}
		statuses[index] = at(exercise["set_statuses"], index)
		if statuses[index] == "failed" {
			failures = true
		}
		reasons[index] = at(exercise["failed_set_reasons"], index)
		if reasons[index] == nil {
			reasons[index] = []any{}
		}
		uniqueValues[valueKey(values[index].reps)+"|"+valueKey(values[index].kg)+"|"+valueKey(values[index].rpe)] = true
		uniqueStatuses[valueKey(statuses[index])] = true
	}
	if len(uniqueValues) == 1 && len(uniqueStatuses) == 1 && !failures {
		merged := pyval.CopyMap(exercise)
		merged["sets"] = int64(len(setsData))
		merged["reps"], merged["kg"], merged["rpe"] = values[0].reps, values[0].kg, values[0].rpe
		return []map[string]any{merged}
	}
	base := map[string]any{}
	for key, value := range exercise {
		if !perSetFields[key] {
			base[key] = value
		}
	}
	rows := make([]map[string]any, 0, len(setsData))
	for index := range setsData {
		row := pyval.CopyMap(base)
		row["sets"] = int64(1)
		row["reps"], row["kg"], row["rpe"] = values[index].reps, values[index].kg, values[index].rpe
		row["set_number"] = int64(index + 1)
		row["failed_set_reasons"] = []any{reasons[index]}
		if index == 0 {
			if notes, present := exercise["notes"]; present {
				row["notes"] = notes
			} else {
				row["notes"] = ""
			}
		} else {
			row["notes"] = ""
		}
		if statuses[index] != nil {
			row["set_statuses"] = []any{statuses[index]}
		}
		if pyval.Truthy(exercise["id"]) {
			row["id"] = fmt.Sprintf("%s-set%d", pyval.Str(exercise["id"]), index+1)
		}
		rows = append(rows, row)
	}
	return rows
}

func expandSessionSets(sessions []any) []any {
	out := make([]any, 0, len(sessions))
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			out = append(out, raw)
			continue
		}
		if exercises, isList := session["exercises"].([]any); isList {
			copied := make(map[string]any, len(session))
			for key, value := range session {
				copied[key] = value
			}
			expanded := []any{}
			for _, item := range exercises {
				if exercise, isMap := item.(map[string]any); isMap {
					for _, row := range expandPerformedSets(exercise) {
						expanded = append(expanded, row)
					}
				}
			}
			copied["exercises"] = expanded
			session = copied
		}
		out = append(out, session)
	}
	return out
}

func (d *Deps) sanitizedItem(ctx context.Context, athlete, sk string) (map[string]any, error) {
	item, err := d.Related.Versioned(ctx, athlete, sk)
	if err != nil || item == nil {
		return nil, err
	}
	sanitized, _ := pyval.Sanitize(item).(map[string]any)
	return sanitized, nil
}

func (d *Deps) maxHistory(ctx context.Context, athlete string, access Access) ([]map[string]any, error) {
	item, err := d.sanitizedItem(ctx, athlete, "max_history#current")
	if err != nil {
		return nil, err
	}
	entries := pyval.Maps(item["entries"])
	history := []string{}
	byID := map[string]map[string]any{}
	var unkeyed []map[string]any
	for _, entry := range entries {
		if pyval.Truthy(entry["entry_id"]) {
			id := pyval.Str(entry["entry_id"])
			if _, seen := byID[id]; !seen {
				history = append(history, id)
			}
			byID[id] = entry
			continue
		}
		unkeyed = append(unkeyed, entry)
	}
	raw, err := d.Related.CompetitionItems(ctx, athlete)
	if err != nil {
		return nil, err
	}
	for _, competition := range raw {
		results, isMap := competition["results"].(map[string]any)
		if competition["user_status"] != "completed" || !isMap {
			continue
		}
		master := competition["master_id"]
		if !pyval.Truthy(master) {
			master = strings.TrimPrefix(pyval.Str2(competition["sk"]), "COMP#")
		}
		identifier := "competition#" + pyval.Str(master)
		date := competition["start_date"]
		if !pyval.Truthy(date) {
			date = competition["date"]
		}
		entry := map[string]any{"entry_id": identifier, "date": date, "context": "Competition result", "bodyweight_kg": competition["body_weight_kg"]}
		sum := new(big.Rat)
		for _, lift := range []string{"squat_kg", "bench_kg", "deadlift_kg"} {
			entry[lift] = results[lift]
			if number, ok := results[lift].(interface{ String() string }); ok && pyval.IsDecimal(results[lift]) {
				parsed, _ := new(big.Rat).SetString(number.String())
				sum.Add(sum, parsed)
			}
		}
		if total := results["total_kg"]; pyval.Truthy(total) {
			entry["total_kg"] = total
		} else {
			entry["total_kg"] = jsonNumberOf(sum)
		}
		sanitized, _ := pyval.Sanitize(entry).(map[string]any)
		if _, seen := byID[identifier]; !seen {
			history = append(history, identifier)
		}
		byID[identifier] = sanitized
	}
	combined := append([]map[string]any(nil), unkeyed...)
	for _, id := range history {
		combined = append(combined, byID[id])
	}
	combined = scopedHistory(combined, access)
	sort.SliceStable(combined, func(i, j int) bool {
		return pyval.Str(combined[i]["date"]) > pyval.Str(combined[j]["date"])
	})
	return combined, nil
}

func jsonNumberOf(value *big.Rat) any {
	if value.IsInt() {
		return pyval.Sanitize(json.Number(value.Num().String()))
	}
	f, _ := value.Float64()
	return f
}

func scopedHistory(entries []map[string]any, access Access) []map[string]any {
	if _, limited := access.readScope(); !limited {
		return entries
	}
	var unlinked, linked []map[string]any
	for _, entry := range entries {
		if !pyval.Truthy(entry["entry_id"]) {
			if entry["context"] != "Competition result" {
				unlinked = append(unlinked, entry)
			}
			continue
		}
		linked = append(linked, entry)
	}
	asList := make([]any, len(linked))
	for index, entry := range linked {
		asList[index] = entry
	}
	visible := map[int]bool{}
	for index, entry := range linked {
		if len(visibleEntries([]any{entry}, access)) > 0 {
			visible[index] = true
			continue
		}
		identifier := strings.TrimPrefix(strings.TrimPrefix(pyval.Str(entry["entry_id"]), "competition#"), "COMP#")
		probe := pyval.CopyMap(entry)
		probe["master_id"] = identifier
		if len(visibleEntries([]any{probe}, access)) > 0 {
			visible[index] = true
		}
	}
	out := append([]map[string]any(nil), unlinked...)
	for index, entry := range linked {
		if visible[index] {
			out = append(out, entry)
		}
	}
	return out
}

func (d *Deps) federationLibrary(ctx context.Context, athlete string) map[string]any {
	fallback := map[string]any{"pk": athlete, "sk": "federations#v1", "updated_at": "", "federations": []any{}, "qualification_standards": []any{}}
	item, err := d.sanitizedItem(ctx, athlete, "federations#v1")
	if err != nil {
		d.Log.Warn("export: federation library fetch failed", "error", err)
		return fallback
	}
	if item == nil {
		return fallback
	}
	return item
}

func exportMarkdown(d *Deps, r *Request) (any, error) {
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, true)
	if err != nil {
		return nil, mapError(err)
	}
	entries, err := d.Related.CompetitionEntries(r.Ctx, r.Athlete, "", "")
	if err != nil {
		return nil, err
	}
	program := make(map[string]any, len(loaded.Program)+1)
	for key, value := range loaded.Program {
		program[key] = value
	}
	program["competitions"] = entriesToList(entries)
	access := Access(r.Access)
	if len(access) > 0 {
		program = ProgramView(program, access)
	}
	sessions, _ := program["sessions"].([]any)
	program["sessions"] = expandSessionSets(sessions)
	permissions := access.permissions()
	allowed := func(domain string) bool { return len(access) == 0 || permissions[domain+":read"] }

	meta, _ := program["meta"].(map[string]any)
	sex := strings.ToLower(pyval.Str(firstTruthy(meta["sex"], "male")))

	input := markdown.Input{Program: program, PK: r.Athlete, Sex: sex}
	input.Federations = d.federationLibrary(r.Ctx, r.Athlete)
	if !allowed("federation") {
		input.Federations = nil
	}
	if item, err := d.sanitizedItem(r.Ctx, r.Athlete, "weight_log#current"); err != nil {
		d.Log.Warn("export: weight log fetch failed", "error", err)
	} else if item != nil && allowed("weight-log") {
		input.WeightLog = pyval.Maps(item["entries"])
	}
	if allowed("performance") {
		history, err := d.maxHistory(r.Ctx, r.Athlete, access)
		if err != nil {
			d.Log.Warn("export: max history fetch failed", "error", err)
		}
		input.MaxHistory = history
	}
	current := pyval.Maps(scope.Program(program, "")["sessions"])
	weeks := effectiveWeeks(current)
	currentWeek := weeks
	found := false
	for _, session := range current {
		if pyval.Truthy(session["week_number"]) {
			week, _ := pyval.Truncate(session["week_number"])
			if !found || week > currentWeek {
				currentWeek, found = week, true
			}
		}
	}
	weekStart := max(1, currentWeek-weeks+1)
	sessionList, _ := scope.Program(program, "")["sessions"].([]any)
	weekly, err := d.Analytics.WeeklyAnalysis(r.Ctx, r.Caller, map[string]any{
		"program": program, "sessions": sessionList, "weeks": int64(max(1, currentWeek-weekStart+1)), "block": "current",
		"week_start": int64(weekStart), "week_end": int64(currentWeek), "ref_date": d.Env.Now().Format("2006-01-02"),
	})
	if err != nil {
		d.Log.Warn("export: weekly_analysis failed", "error", err)
	} else if allowed("analytics") {
		input.Weekly = weekly.Data
		input.LiftOrder = weekly.LiftOrder
	}
	input.Today, _ = time.Parse("2006-01-02", d.Today())
	rendered, err := markdown.Render(markdown.Input{
		Program: scope.Program(program, ""), Weekly: input.Weekly, WeightLog: input.WeightLog, MaxHistory: input.MaxHistory,
		Federations: input.Federations, LiftOrder: input.LiftOrder, PK: input.PK, Sex: input.Sex, Today: input.Today,
	})
	if err != nil {
		return nil, err
	}
	return map[string]any{"markdown": rendered, "length": int64(utf8.RuneCountInString(rendered))}, nil
}

func effectiveWeeks(sessions []map[string]any) int {
	var dates []string
	for _, session := range sessions {
		if pyval.Truthy(session["date"]) {
			dates = append(dates, pyval.Str(session["date"]))
		}
	}
	if len(dates) == 0 {
		return 4
	}
	sort.Strings(dates)
	first, okFirst := parseDay(dates[0])
	last, okLast := parseDay(dates[len(dates)-1])
	if !okFirst || !okLast {
		return 4
	}
	days := math.Abs(last.Sub(first).Hours() / 24)
	return max(int(days/7+0.999), 4)
}

func parseDay(value string) (time.Time, bool) {
	if len(value) > 10 {
		value = value[:10]
	}
	parsed, err := time.Parse("2006-01-02", value)
	return parsed, err == nil
}
