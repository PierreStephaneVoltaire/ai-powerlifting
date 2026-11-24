package apply

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"

	"powerlifting/templates/internal/payload"
)

var weekdays = []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}

func text(v any) string { s, _ := v.(string); return s }
func number(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case int:
		return float64(x)
	case json.Number:
		n, _ := x.Float64()
		return n
	case string:
		n, _ := strconv.ParseFloat(x, 64)
		return n
	}
	return 0
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
func weekDay(value string) string {
	for _, day := range weekdays {
		if strings.EqualFold(strings.TrimSpace(value), day) {
			return day
		}
	}
	return "Monday"
}
func weekdayIndex(day string) int {
	for i, value := range weekdays {
		if value == day {
			return i
		}
	}
	return 0
}
func Missing(template map[string]any, maxes map[string]any, glossary []map[string]any) []string {
	byID := map[string]map[string]any{}
	for _, entry := range glossary {
		byID[text(entry["id"])] = entry
	}
	required := map[string]bool{}
	for _, session := range maps(template["sessions"]) {
		for _, ex := range maps(session["exercises"]) {
			if ex["load_type"] == "percentage" && text(ex["glossary_id"]) != "" {
				required[text(ex["glossary_id"])] = true
			}
		}
	}
	missing := []string{}
	for id := range required {
		if id == "squat" || id == "bench" || id == "deadlift" {
			if number(maxes[id]) == 0 {
				missing = append(missing, id)
			}
			continue
		}
		if byID[id] == nil || byID[id]["e1rm_estimate"] == nil {
			missing = append(missing, id)
		}
	}
	sort.Strings(missing)
	return missing
}
func Concretize(template map[string]any, maxes map[string]any, glossary []map[string]any, start time.Time, startDay string) ([]map[string]any, error) {
	byID := map[string]map[string]any{}
	for _, entry := range glossary {
		byID[text(entry["id"])] = entry
	}
	startDay = weekDay(startDay)
	start = time.Date(start.Year(), start.Month(), start.Day(), 0, 0, 0, 0, time.UTC)
	startIndex := weekdayIndex(startDay)
	dateIndex := (int(start.Weekday()) + 6) % 7
	anchor := start.AddDate(0, 0, -((dateIndex - startIndex + 7) % 7))
	result := []map[string]any{}
	for _, session := range maps(template["sessions"]) {
		week := int(number(session["week_number"]))
		if week == 0 {
			week = 1
		}
		offset := 0
		day := text(session["day_of_week"])
		found := false
		for i, name := range weekdays {
			if name == day {
				offset = (i - startIndex + 7) % 7
				found = true
				break
			}
		}
		if !found {
			index := int(number(session["day_index"]))
			if index >= 1 && index <= 7 {
				offset = index - 1
			} else {
				offset = max(0, min(6, index))
			}
		}
		date := anchor.AddDate(0, 0, (week-1)*7+offset)
		if date.Before(start) {
			continue
		}
		planned := []map[string]any{}
		for _, original := range maps(session["exercises"]) {
			ex, err := payload.Clone(original)
			if err != nil {
				return nil, err
			}
			if err = payload.NormalizePrescription(ex); err != nil {
				return nil, err
			}
			gid := text(ex["glossary_id"])
			loadType := text(ex["load_type"])
			if loadType == "" {
				loadType = "unresolvable"
			}
			source := loadType
			load := number(ex["load_value"])
			var kg any
			rpe := ex["rpe_target"]
			if rpe == nil && loadType == "rpe" {
				rpe = ex["load_value"]
			}
			e1rm := number(maxes[gid])
			if e1rm == 0 {
				if entry := byID[gid]; entry != nil {
					if estimate, ok := entry["e1rm_estimate"].(map[string]any); ok {
						e1rm = number(estimate["value_kg"])
					}
				}
			}
			switch loadType {
			case "percentage":
				if load != 0 {
					if e1rm != 0 {
						kg = math.RoundToEven(e1rm*load/2.5) * 2.5
					} else {
						source = "unresolvable"
					}
				}
			case "absolute":
				kg = ex["load_value"]
			case "rpe":
				if ex["rep_mode"] != "amrap" && ex["rep_unit"] != "minutes" && ex["rep_unit"] != "seconds" {
					reps, target := number(ex["reps"]), number(rpe)
					if reps > 0 && target > 0 && e1rm != 0 {
						pct := 1 / (1 + (reps+math.Max(0, 10-target))/30)
						kg = math.RoundToEven(e1rm*pct/2.5) * 2.5
						source = "rpe_estimate"
					}
				}
			}
			notes := ex["notes"]
			if notes == nil {
				notes = ""
			}
			plannedEx := map[string]any{"name": ex["name"], "glossary_id": ex["glossary_id"], "sets": ex["sets"], "reps": ex["reps"], "kg": kg, "rpe_target": rpe, "load_source": source, "notes": notes}
			if ex["rep_mode"] == "amrap" {
				plannedEx["rep_mode"] = "amrap"
			}
			if ex["rep_unit"] != nil {
				plannedEx["rep_unit"] = ex["rep_unit"]
			}
			planned = append(planned, plannedEx)
		}
		label := session["label"]
		if label == nil {
			label = fmt.Sprintf("W%d", week)
		}
		result = append(result, map[string]any{"date": date.Format("2006-01-02"), "day": date.Weekday().String(), "week": label, "week_number": week, "status": "planned", "completed": false, "planned_exercises": planned, "exercises": []any{}, "session_notes": ""})
	}
	return result, nil
}
