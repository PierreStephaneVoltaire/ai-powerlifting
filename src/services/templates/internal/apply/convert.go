package apply

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math"
	"sort"
	"time"

	"powerlifting/templates/internal/payload"
)

func Convert(program map[string]any, maxes map[string]any) (map[string]any, error) {
	meta, _ := program["meta"].(map[string]any)
	start, hasStart := time.Parse("2006-01-02", text(meta["program_start"]))
	weeks := map[int]int{}
	maxWeek := 0
	sessions := []map[string]any{}
	for _, source := range maps(program["sessions"]) {
		date, err := time.Parse("2006-01-02", text(source["date"]))
		if err != nil {
			return nil, fmt.Errorf("invalid session date: %w", err)
		}
		week := int(number(source["week_number"]))
		if week == 0 {
			week = 1
		}
		if hasStart == nil {
			week = int(math.Floor(date.Sub(start).Hours()/24/7)) + 1
		}
		weeks[week]++
		if week > maxWeek {
			maxWeek = week
		}
		if source["completed"] == true || source["status"] == "logged" || source["status"] == "completed" {
			continue
		}
		rawExercises := source["planned_exercises"]
		if len(maps(rawExercises)) == 0 {
			rawExercises = source["exercises"]
		}
		exercises := []any{}
		for _, original := range maps(rawExercises) {
			ex, err := payload.Clone(original)
			if err != nil {
				return nil, err
			}
			if err = payload.NormalizePrescription(ex); err != nil {
				return nil, err
			}
			name := text(ex["name"])
			if name == "" {
				continue
			}
			kg, e1rm := number(ex["kg"]), number(maxes[name])
			rpe := ex["rpe_target"]
			if rpe == nil || number(rpe) == 0 {
				rpe = ex["rpe"]
			}
			source := text(ex["load_source"])
			if source == "" {
				source = "absolute"
			}
			timed := ex["rep_unit"] == "seconds" || ex["rep_unit"] == "minutes"
			loadType := "unresolvable"
			var loadValue any
			switch {
			case source == "rpe" || source == "rpe_estimate" || (kg == 0 && number(rpe) != 0):
				loadType, loadValue = "rpe", rpe
			case kg > 0 && e1rm > 0 && (!timed || source == "percentage"):
				loadType, loadValue = "percentage", math.RoundToEven(kg/e1rm*1000)/1000
			case kg > 0:
				loadType, loadValue = "absolute", ex["kg"]
			default:
				if timed {
					loadType = "duration"
				}
				rpe = nil
			}
			notes := ex["notes"]
			if notes == nil {
				notes = ""
			}
			exercise := map[string]any{"name": name, "glossary_id": ex["glossary_id"], "sets": ex["sets"], "reps": ex["reps"], "notes": notes, "load_type": loadType, "load_value": loadValue, "rpe_target": rpe}
			if ex["rep_mode"] == "amrap" {
				exercise["rep_mode"] = "amrap"
				exercise["reps"] = nil
			}
			if ex["rep_unit"] != nil {
				exercise["rep_unit"] = ex["rep_unit"]
			}
			exercises = append(exercises, exercise)
		}
		var random [16]byte
		if _, err := rand.Read(random[:]); err != nil {
			return nil, err
		}
		dayIndex := (int(date.Weekday())+6)%7 + 1
		label := source["week"]
		if label == nil {
			label = ""
		}
		sessions = append(sessions, map[string]any{"id": "tpl_" + hex.EncodeToString(random[:]), "week_number": week, "day_of_week": source["day"], "day_index": dayIndex, "label": label, "exercises": exercises})
	}
	sort.SliceStable(sessions, func(i, j int) bool {
		wi, wj := sessions[i]["week_number"].(int), sessions[j]["week_number"].(int)
		if wi != wj {
			return wi < wj
		}
		return sessions[i]["day_index"].(int) < sessions[j]["day_index"].(int)
	})
	days := 0
	for _, count := range weeks {
		if count > days {
			days = count
		}
	}
	name := text(meta["program_name"])
	if name == "" {
		name = "Block"
	}
	phases := program["phases"]
	if phases == nil {
		phases = []any{}
	}
	list := make([]any, len(sessions))
	for i, session := range sessions {
		list[i] = session
	}
	return map[string]any{"meta": map[string]any{"name": "Template from " + name, "description": fmt.Sprintf("Automatically converted from program %v", program["sk"]), "estimated_weeks": maxWeek, "days_per_week": days, "archived": false, "derived_from_program_sk": program["sk"]}, "phases": phases, "sessions": list}, nil
}
