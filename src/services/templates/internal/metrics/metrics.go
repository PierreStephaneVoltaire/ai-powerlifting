package metrics

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"powerlifting/templates/internal/payload"
)

//go:embed calculation_constants.json
var constants []byte

var rpePercent = func() map[string]float64 {
	var data struct {
		RPE map[string]float64 `json:"rpe_percent"`
	}
	if err := json.Unmarshal(constants, &data); err != nil {
		panic(err)
	}
	return data.RPE
}()

var invalidName = regexp.MustCompile(`[^a-z0-9 ]+`)
var liftNames = map[string]string{"squat": "Squat", "bench": "Bench Press", "deadlift": "Deadlift"}
var allowedSuffix = map[string]bool{"heavy": true, "light": true, "single": true, "singles": true, "double": true, "triple": true, "backoff": true, "backoffs": true, "back": true, "off": true, "top": true, "set": true, "test": true, "deload": true, "opener": true, "second": true, "third": true, "attempt": true, "work": true, "working": true, "volume": true, "intensity": true, "comp": true, "competition": true}

func text(v any) string { s, _ := v.(string); return s }
func number(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int:
		return float64(n)
	case json.Number:
		value, _ := n.Float64()
		return value
	case string:
		value, _ := strconv.ParseFloat(n, 64)
		return value
	}
	return 0
}
func normalize(s string) string {
	return strings.TrimSpace(invalidName.ReplaceAllString(strings.ToLower(s), " "))
}
func lift(name string) string {
	words := strings.Fields(normalize(name))
	if len(words) == 0 {
		return ""
	}
	n := 1
	if len(words) > 1 && words[0] == "bench" && words[1] == "press" {
		n = 2
	}
	result := words[0]
	if result != "squat" && result != "bench" && result != "deadlift" {
		return ""
	}
	for _, word := range words[n:] {
		if !allowedSuffix[word] {
			if _, err := strconv.Atoi(word); err != nil {
				return ""
			}
		}
	}
	return result
}
func maps(v any) []map[string]any {
	list, _ := v.([]any)
	result := make([]map[string]any, 0, len(list))
	for _, item := range list {
		if m, ok := item.(map[string]any); ok {
			result = append(result, m)
		}
	}
	return result
}
func sortedSet(s map[string]bool) []string {
	out := make([]string, 0, len(s))
	for key := range s {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}
func modes(ex map[string]any) (string, float64) {
	if ex["rep_unit"] == "minutes" || ex["rep_unit"] == "seconds" {
		return "timed", 0
	}
	kind := strings.ToLower(text(ex["load_type"]))
	value := number(ex["load_value"])
	if value != 0 {
		switch kind {
		case "absolute":
			return "absolute", value
		case "percentage", "percent":
			if value > 1.5 {
				value /= 100
			}
			return "percentage", value
		case "rpe":
			return "rpe", value
		}
	}
	if target := number(ex["rpe_target"]); target != 0 {
		return "rpe", target
	}
	return "user_selected", 8
}
func round(v float64, places float64) float64 { return math.RoundToEven(v*places) / places }

type exerciseSummary struct {
	entry            map[string]any
	modes, sources   map[string]bool
	minWeek, maxWeek int
}

func Program(template map[string]any, glossary []map[string]any, currentMaxes map[string]any, profiles []any, now time.Time) (map[string]any, map[string]any, error) {
	byID := map[string]map[string]any{}
	byName := map[string]map[string]any{}
	profilesKnown := map[string]bool{}
	for _, entry := range glossary {
		if id := text(entry["id"]); id != "" {
			byID[id] = entry
		}
		if name := text(entry["name"]); name != "" {
			byName[normalize(name)] = entry
		}
		fatigue, _ := entry["fatigue_profile"].(map[string]any)
		if fatigue != nil {
			valid := true
			for _, key := range []string{"axial", "neural", "peripheral", "systemic"} {
				if _, ok := fatigue[key]; !ok {
					valid = false
				}
			}
			if valid {
				profilesKnown[strings.ToLower(strings.TrimSpace(text(entry["name"])))] = true
			}
		}
	}
	maxes := map[string]any{}
	for key := range liftNames {
		if v := number(currentMaxes[key]); v != 0 {
			maxes[key] = v
		}
	}
	date := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	start := date.AddDate(0, 0, -((int(date.Weekday()) + 6) % 7))
	sessions := []any{}
	summaries := map[string]*exerciseSummary{}
	workloads := map[string]any{}
	top := map[int]map[string]float64{}
	missing := map[string]bool{}
	unavailable := map[string]bool{}
	days := []string{"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
	for _, session := range maps(template["sessions"]) {
		week := int(number(session["week_number"]))
		if week <= 0 {
			continue
		}
		key := strconv.Itoa(week)
		workload, ok := workloads[key].(map[string]any)
		if !ok {
			workload = map[string]any{"lifting_sets": float64(0), "amrap_sets": float64(0), "cardio_minutes": float64(0), "muscle_sets": map[string]any{}}
			workloads[key] = workload
		}
		planned := []any{}
		for _, original := range maps(session["exercises"]) {
			ex, err := payload.Clone(original)
			if err != nil {
				return nil, nil, err
			}
			if err = payload.NormalizePrescription(ex); err != nil {
				return nil, nil, err
			}
			sets, reps := number(ex["sets"]), number(ex["reps"])
			if sets <= 0 {
				continue
			}
			name := text(ex["name"])
			entry := byID[text(ex["glossary_id"])]
			if entry == nil {
				entry = byName[normalize(name)]
			}
			liftKey := lift(name)
			if entry == nil && liftKey != "" {
				entry = byName[normalize(liftNames[liftKey])]
			}
			category := text(entry["category"])
			variation := ""
			if liftKey == "" && (category == "squat" || category == "bench" || category == "deadlift") {
				variation = category
			}
			canonical := text(entry["name"])
			if canonical == "" {
				canonical = name
			}
			if liftKey != "" {
				canonical = liftNames[liftKey]
			}
			mode, value := modes(ex)
			e1rm := number(maxes[liftKey])
			if liftKey == "" {
				candidate := entry["e1rm_estimate"]
				emptyEstimate, isMap := candidate.(map[string]any)
				if candidate == nil || isMap && len(emptyEstimate) == 0 || candidate == "" || candidate == float64(0) || candidate == int(0) {
					candidate = entry["e1rm"]
				}
				if data, ok := candidate.(map[string]any); ok {
					for _, field := range []string{"value_kg", "kg", "e1rm_kg", "estimate_kg"} {
						if number(data[field]) != 0 {
							candidate = data[field]
							break
						}
					}
				}
				e1rm = number(candidate)
			}
			kg := float64(0)
			source := ""
			switch mode {
			case "absolute":
				kg, source = value, "prescribed_kg"
			case "percentage":
				if e1rm != 0 {
					kg, source = value*e1rm, "percent_of_e1rm"
				}
			case "rpe", "user_selected":
				if e1rm != 0 {
					if pct := rpePercent[fmt.Sprintf("%d-%d", int(reps), int(value))]; pct != 0 {
						kg, source = pct*e1rm, "rpe_table_of_e1rm"
					}
				}
			}
			if mode == "timed" {
				duration := reps
				if ex["rep_unit"] == "seconds" {
					duration /= 60
				}
				workload["cardio_minutes"] = number(workload["cardio_minutes"]) + sets*duration
			} else {
				workload["lifting_sets"] = number(workload["lifting_sets"]) + sets
				if ex["rep_mode"] == "amrap" {
					workload["amrap_sets"] = number(workload["amrap_sets"]) + sets
				}
				muscles := workload["muscle_sets"].(map[string]any)
				for field, multiplier := range map[string]float64{"primary_muscles": 1, "secondary_muscles": .5, "tertiary_muscles": .25} {
					if values, ok := entry[field].([]any); ok {
						for _, raw := range values {
							muscle := text(raw)
							muscles[muscle] = number(muscles[muscle]) + sets*multiplier
						}
					}
				}
			}
			if !profilesKnown[strings.ToLower(strings.TrimSpace(canonical))] {
				missing[name] = true
			}
			if mode != "timed" && kg != 0 && reps > 0 {
				var rpe any
				if mode == "rpe" || mode == "user_selected" {
					rpe = value
				}
				planned = append(planned, map[string]any{"name": canonical, "kg": round(kg, 100), "reps": int(reps), "sets": sets, "rpe": rpe})
				if liftKey != "" {
					if top[week] == nil {
						top[week] = map[string]float64{}
					}
					top[week][liftKey] = math.Max(kg, top[week][liftKey])
				}
			} else if mode != "timed" {
				unavailable[name] = true
			}
			summary := summaries[name]
			if summary == nil {
				role := "accessory"
				target := variation
				if liftKey != "" {
					role, target = "competition_lift", liftKey
				} else if variation != "" {
					role = "variation"
				}
				var targetValue any
				if target != "" {
					targetValue = target
				}
				summary = &exerciseSummary{entry: map[string]any{"glossary_match": entry["name"], "fatigue_profile": entry["fatigue_profile"], "role": role, "lift": targetValue}, modes: map[string]bool{}, sources: map[string]bool{}, minWeek: week, maxWeek: week}
				summaries[name] = summary
			}
			summary.modes[mode] = true
			if source != "" {
				summary.sources[source] = true
			}
			summary.minWeek = min(summary.minWeek, week)
			summary.maxWeek = max(summary.maxWeek, week)
			if mode == "timed" && (ex["load_type"] == "rpe" || ex["load_type"] == "percentage" || ex["load_type"] == "absolute") {
				summary.entry["timed_load_type"], summary.entry["timed_load_value"], summary.entry["timed_rpe_target"] = ex["load_type"], ex["load_value"], ex["rpe_target"]
			}
		}
		offset := -1
		for i, day := range days {
			if day == strings.ToLower(text(session["day_of_week"])) {
				offset = i
				break
			}
		}
		if offset < 0 {
			offset = int(number(session["day_index"])) % 7
			if offset < 0 {
				offset += 7
			}
		}
		sessions = append(sessions, map[string]any{"date": start.AddDate(0, 0, (week-1)*7+offset).Format("2006-01-02"), "week_number": week, "day": session["day_of_week"], "completed": true, "status": "logged", "exercises": planned})
	}
	phases := []any{}
	for _, phase := range maps(template["phases"]) {
		phases = append(phases, map[string]any{"name": phase["name"], "intent": phase["intent"], "start_week": int(number(phase["week_start"])), "end_week": int(number(phase["week_end"])), "target_rpe_min": phase["target_rpe_min"], "target_rpe_max": phase["target_rpe_max"]})
	}
	exercises := map[string]any{}
	for name, item := range summaries {
		item.entry["load_modes"], item.entry["planned_load_sources"], item.entry["weeks"] = sortedSet(item.modes), sortedSet(item.sources), fmt.Sprintf("%d-%d", item.minWeek, item.maxWeek)
		exercises[name] = item.entry
	}
	topPercent := map[string]any{}
	for week, lifts := range top {
		result := map[string]any{}
		for name, kg := range lifts {
			if maximum := number(maxes[name]); maximum != 0 {
				result[name] = round(kg/maximum*100, 10)
			}
		}
		topPercent[strconv.Itoa(week)] = result
	}
	program := map[string]any{"meta": map[string]any{"program_start": start.Format("2006-01-02"), "current_block_id": "current"}, "phases": phases, "sessions": sessions, "current_maxes": maxes, "lift_profiles": profiles, "competitions": []any{}}
	summary := map[string]any{"exercises": exercises, "top_set_pct_of_current_max_by_week": topPercent, "weekly_prescriptions": workloads, "missing_from_glossary": sortedSet(missing), "load_not_computable": sortedSet(unavailable)}
	return program, summary, nil
}

func Result(program, summary map[string]any, analyze func(map[string]any) (map[string]any, error)) map[string]any {
	sessions, _ := program["sessions"].([]any)
	if len(sessions) == 0 {
		return map[string]any{"weeks": 0}
	}
	weeks := 0
	end := ""
	for _, session := range maps(sessions) {
		weeks = max(weeks, int(number(session["week_number"])))
		if date := text(session["date"]); date > end {
			end = date
		}
	}
	report, err := analyze(map[string]any{"program": program, "sessions": sessions, "week_start": 1, "week_end": weeks, "ref_date": end, "block": "", "current_maxes": program["current_maxes"]})
	if err != nil || report == nil {
		report = map[string]any{}
	}
	for _, key := range []string{"week", "window_start", "window_end", "selected_session_context", "compliance", "estimated_dots", "estimated_dots_reason", "projections", "projection_reason", "projection_calibration", "readiness_score", "attempt_selection", "specificity_target_competition", "taper_quality", "peaking_timeline", "sessions_analyzed"} {
		delete(report, key)
	}
	return map[string]any{"weeks": weeks, "analysis": report, "template": summary, "notes": []string{
		"analysis is the app's weekly analysis report computed on this template alone, as if every planned session were completed as written. No logged training is included.",
		"Planned kg comes from the prescription, or the percent or RPE table applied to the current max (competition lifts) or the glossary e1RM (other exercises).",
		"missing_from_glossary exercises fall back to the app's default fatigue profile; load_not_computable exercises have no kg and are excluded from load-based metrics.",
		"Unloaded resistance work defaults to RPE 8. Weekly muscle sets count primary muscles at 1, secondary at 0.5 and tertiary at 0.25 per prescribed set. Cardio minutes are recorded separately.",
	}}
}
