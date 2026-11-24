package service

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"strings"
	"time"

	"powerlifting/templates/internal/apperr"
	"powerlifting/templates/internal/apply"
	"powerlifting/templates/internal/auth"
)

func (s *Service) confirmNewBlock(ctx context.Context, args map[string]any, caller auth.Caller, owners []string) (any, error) {
	if s.Sources == nil || s.Domain == nil {
		return nil, apperr.Upstream("Program source unavailable")
	}
	template, err := s.Library.Get(ctx, value(args["sk"]), owners)
	if err != nil {
		return nil, err
	}
	program, err := s.Sources.Program(ctx, caller.Athlete, "")
	if err != nil {
		return nil, apperr.Upstream("Program source unavailable")
	}
	glossary, err := s.Sources.Glossary(ctx, caller.Athlete)
	if err != nil {
		return nil, apperr.Upstream("Glossary source unavailable")
	}
	maxes := map[string]any{}
	if existing, ok := program["current_maxes"].(map[string]any); ok {
		for key, item := range existing {
			maxes[key] = item
		}
	}
	if supplied, ok := args["backfilled_maxes"].(map[string]any); ok {
		for key, item := range supplied {
			maxes[key] = item
		}
	}
	if missing := apply.Missing(template, maxes, glossary); len(missing) != 0 {
		return nil, apperr.Validation("missing maxes or exercise resolution: " + strings.Join(missing, ", "))
	}
	weekDay := "Monday"
	for _, day := range []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"} {
		if strings.EqualFold(strings.TrimSpace(value(args["week_start_day"])), day) {
			weekDay = day
			break
		}
	}
	start := time.Now()
	if date := value(args["start_date"]); date != "" {
		start, err = time.Parse("2006-01-02", date)
		if err != nil {
			return nil, apperr.Validation("Invalid start date")
		}
	}
	sessions, err := apply.Concretize(template, maxes, glossary, start, weekDay)
	if err != nil {
		return nil, apperr.Validation(err.Error())
	}
	phases := []any{}
	for _, raw := range asList(template["phases"]) {
		phase, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		copy := map[string]any{}
		for key, item := range phase {
			if key != "week_start" && key != "week_end" {
				copy[key] = item
			}
		}
		copy["start_week"] = defaultValue(defaultValue(phase["start_week"], phase["week_start"]), 1)
		copy["end_week"] = defaultValue(defaultValue(phase["end_week"], phase["week_end"]), copy["start_week"])
		phases = append(phases, copy)
	}
	meta, _ := program["meta"].(map[string]any)
	blocks := asList(meta["blocks"])
	var active, completed map[string]any
	for _, raw := range blocks {
		block, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		status := defaultValue(block["status"], "active")
		if status == "active" && active == nil {
			active = block
		}
		if status == "completed" {
			completed = block
		}
	}
	if len(blocks) == 0 {
		active = map[string]any{"id": "current"}
	}
	anchor, action := active, "complete_and_start"
	if anchor == nil {
		anchor, action = completed, "start_next"
	}
	source := value(anchor["id"])
	if source == "" {
		source = value(anchor["block_id"])
	}
	if source == "" {
		source = value(args["block_id"])
	}
	if source == "" {
		source = "current"
	}
	positive := map[string]any{}
	for key, raw := range maxes {
		switch number := raw.(type) {
		case float64:
			if number > 0 && !math.IsInf(number, 0) {
				positive[key] = number
			}
		case int:
			if number > 0 {
				positive[key] = number
			}
		case json.Number:
			if parsed, err := number.Float64(); err == nil && parsed > 0 && !math.IsInf(parsed, 0) {
				positive[key] = parsed
			}
		}
	}
	request := map[string]any{"pk": caller.Athlete, "action": action, "block_id": source, "start_date": start.Format("2006-01-02"), "week_start_day": weekDay, "start_maxes_kg": positive, "next_program": map[string]any{"phases": phases, "sessions": sessions}}
	if name := value(args["block_name"]); name != "" {
		request["name"] = name
	}
	result, err := s.Domain.Call(ctx, "program", "block_transition", request, caller)
	if err != nil {
		return nil, fmt.Errorf("block transition: %w", err)
	}
	written, _ := result["program"].(map[string]any)
	writtenMeta, _ := written["meta"].(map[string]any)
	version := writtenMeta["version_label"]
	sk := defaultValue(written["sk"], version)
	return map[string]any{"status": "applied", "program_version": version, "program_sk": sk, "target": "new_block", "block_id": result["next_block_id"], "preserved_sessions": len(asList(program["sessions"]))}, nil
}

func asList(value any) []any { list, _ := value.([]any); return list }
