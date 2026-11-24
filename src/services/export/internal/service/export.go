package service

import (
	"context"
	"encoding/base64"
	"fmt"
	"math"
	"net/http"
	"sort"
	"strings"
	"time"

	"powerlifting/export/internal/apperr"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/cache"
	"powerlifting/export/internal/markdown"
	"powerlifting/export/internal/publication"
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
	"powerlifting/export/internal/workbook"
)

func (s *Service) export(ctx context.Context, name string, args, access map[string]any, caller auth.Caller) (any, error) {
	if name == "get_analysis_markdown" || name == "analytics.markdown" {
		return s.markdown(ctx, args, access, caller)
	}
	if name == "export_program_history" {
		return s.history(ctx, args, access, caller)
	}
	return nil, &apperr.Error{Status: http.StatusServiceUnavailable, Code: "unavailable", Message: "Export rewrite is incomplete"}
}

func hasPermission(access map[string]any, permission string) bool {
	if self, _ := access["is_self"].(bool); self {
		return true
	}
	switch list := access["permissions"].(type) {
	case []any:
		for _, value := range list {
			if value == permission {
				return true
			}
		}
	case []string:
		for _, value := range list {
			if value == permission {
				return true
			}
		}
	}
	return false
}

func (s *Service) history(ctx context.Context, args, access map[string]any, caller auth.Caller) (any, error) {
	format, err := report.NormalizeFormat(values.Str2(args["format"]))
	if err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if s.Programs == nil {
		return nil, &apperr.Error{Status: http.StatusServiceUnavailable, Code: "unavailable", Message: "Program source unavailable"}
	}
	athlete := values.Str2(args["pk"])
	block := values.Str2(args["block"])
	if block == "" {
		block = "current"
	}
	start, end := values.Str2(args["window_start"]), values.Str2(args["window_end"])
	loaded, err := s.Programs.Load(ctx, athlete, block, start, end, access)
	if err != nil {
		return nil, err
	}
	program := loaded.Program
	window := map[string]any{}
	for _, field := range []string{"window_key", "window_start", "window_end", "week_start", "week_end"} {
		if value, ok := args[field]; ok && value != nil && value != "" {
			window[field] = value
		}
	}
	sessions, _ := program["sessions"].([]any)
	sessions = report.SessionsInWindow(sessions, window)
	program["sessions"] = report.ExpandSessionSets(sessions)
	dates := []string{}
	for _, raw := range sessions {
		session, _ := raw.(map[string]any)
		date := values.Str2(session["date"])
		if len(date) >= 10 {
			dates = append(dates, date[:10])
		}
	}
	sort.Strings(dates)
	entryStart, entryEnd := report.EntryWindow(program, block, window, sessions)
	if notes, ok := program["diet_notes"].([]any); ok {
		filtered := []any{}
		if entryStart != "" && entryEnd != "" {
			for _, raw := range notes {
				note, _ := raw.(map[string]any)
				date := values.Str2(note["date"])
				if len(date) > 10 {
					date = date[:10]
				}
				if entryStart <= date && date <= entryEnd {
					filtered = append(filtered, note)
				}
			}
		}
		program["diet_notes"] = filtered
	}
	name := report.BlockName(program, block)
	meta, _ := program["meta"].(map[string]any)
	if meta == nil {
		meta = map[string]any{}
	}
	meta["program_name"] = name
	program["meta"] = meta
	caller.Athlete = athlete
	historyStart, historyEnd := start, end
	if len(dates) > 0 {
		if historyStart == "" {
			historyStart = dates[0]
		}
		if historyEnd == "" {
			historyEnd = dates[len(dates)-1]
		}
	}
	context := s.historyData(ctx, caller, program, access, window, sessions, block, loaded.Version, historyStart, historyEnd)
	var weekly map[string]any
	if s.Analytics != nil && hasPermission(access, "analytics:read") {
		weeks := 1
		if len(dates) > 1 {
			firstDate, firstErr := time.Parse("2006-01-02", dates[0])
			lastDate, lastErr := time.Parse("2006-01-02", dates[len(dates)-1])
			if firstErr == nil && lastErr == nil {
				weeks = max(1, int(math.Ceil(lastDate.Sub(firstDate).Hours()/24/7)))
			}
		}
		params := map[string]any{"block": block, "weeks": weeks}
		for _, field := range []string{"window_start", "window_end", "week_start", "week_end"} {
			if value, ok := window[field]; ok {
				params[field] = value
			}
		}
		first, last := 0, 0
		for _, raw := range sessions {
			session, _ := raw.(map[string]any)
			week := values.Int(session["week_number"], 0)
			if week > 0 && (first == 0 || week < first) {
				first = week
			}
			if week > last {
				last = week
			}
		}
		if startWeek, ok := window["week_start"]; ok {
			first = values.Int(startWeek, first)
		}
		if endWeek, ok := window["week_end"]; ok {
			last = values.Int(endWeek, last)
		}
		if len(window) == 0 && first > 0 && last >= first {
			params["week_start"], params["week_end"] = first, last
		} else if window["week_start"] != nil && window["week_end"] != nil && last >= first {
			params["weeks"] = last - first + 1
		}
		refDate := end
		if refDate == "" {
			if len(window) == 0 && len(dates) > 0 {
				refDate = dates[len(dates)-1]
			} else {
				refDate = s.Now().UTC().Format("2006-01-02")
			}
		}
		params["ref_date"] = refDate
		caller.Athlete = athlete
		weekly, _ = s.Analytics.Weekly(ctx, caller, params)
	}
	extension := "xlsx"
	var content []byte
	if format == "markdown" {
		extension = "md"
		version := ""
		if loaded.Version > 0 {
			version = fmt.Sprintf("v%03d", loaded.Version)
		}
		text, err := markdown.Render(markdown.Input{Program: program, Weekly: weekly, PK: athlete, Version: version, Sex: strings.ToLower(values.Str2(meta["sex"])), Today: s.Now().UTC(), WeightLog: context.WeightLog, MaxHistory: context.MaxHistory, Federations: context.Federations, Correlation: context.Correlation, Evaluation: context.Evaluation})
		if err != nil {
			return nil, err
		}
		content = []byte(text)
	} else {
		content, err = workbook.Render(program, weekly, context)
		if err != nil {
			return nil, err
		}
	}
	return map[string]any{"filename": report.Filename(program, block, window, extension), "format": format, "content_base64": base64.StdEncoding.EncodeToString(content)}, nil
}

func (s *Service) markdown(ctx context.Context, args, access map[string]any, caller auth.Caller) (any, error) {
	athlete, _ := args["pk"].(string)
	scope, err := cache.ScopeKey(access)
	if err != nil {
		return nil, err
	}
	version := "0"
	if s.Cache != nil {
		if value, err := s.Cache.Version(ctx, athlete); err == nil && value != "" {
			version = value
		}
	}
	key := fmt.Sprintf("pl:markdown:%s:%s:%s:%s", athlete, scope, s.Now().UTC().Format("2006-01-02"), version)
	refresh, _ := args["refresh"].(bool)
	if !refresh && s.Cache != nil {
		record, err := s.Cache.Get(ctx, key)
		if err == nil && record != nil {
			self, _ := access["is_self"].(bool)
			requirements, _ := record["access_requirements"].(map[string]any)
			if !self && !cache.Authorize(requirements, access) {
				return nil, apperr.Forbidden("Access to this saved result has changed")
			}
			return map[string]any{"markdown": record["markdown"], "generated_at": record["generated_at"], "cached": true}, nil
		}
	}
	if cacheOnly, _ := args["cache_only"].(bool); cacheOnly {
		return map[string]any{"cached": false, "cache_miss": true}, nil
	}
	if s.Programs == nil {
		return nil, &apperr.Error{Status: http.StatusServiceUnavailable, Code: "unavailable", Message: "Program source unavailable"}
	}
	loaded, err := s.Programs.Load(ctx, athlete, "current", "", "", nil)
	if err != nil {
		return nil, err
	}
	program := publication.MarkdownView(loaded.Program, publication.Access(access))
	sessions, _ := program["sessions"].([]any)
	week := 1
	for _, raw := range sessions {
		session, _ := raw.(map[string]any)
		if value := values.Int(session["week_number"], 0); value > week {
			week = value
		}
	}
	var weekly map[string]any
	if s.Analytics != nil {
		caller.Athlete = athlete
		weekly, _ = s.Analytics.Weekly(ctx, caller, map[string]any{"program": program, "sessions": sessions, "weeks": week, "block": "current", "week_start": 1, "week_end": week, "ref_date": s.Now().UTC().Format("2006-01-02")})
	}
	sex := "undisclosed"
	if hasPermission(access, "profile:read") {
		sex = "male"
	}
	if sex != "undisclosed" {
		meta, _ := program["meta"].(map[string]any)
		settings, _ := program["settings"].(map[string]any)
		if value, ok := meta["sex"].(string); ok && value != "" {
			sex = value
		} else if value, ok := settings["sex"].(string); ok && value != "" {
			sex = value
		}
	}
	document, err := markdown.Render(markdown.Input{Program: program, Weekly: weekly, PK: athlete, Sex: sex, Today: s.Now().UTC()})
	if err != nil {
		return nil, err
	}
	record := map[string]any{"markdown": document, "generated_at": s.Now().UTC().Format(time.RFC3339Nano)}
	if self, _ := access["is_self"].(bool); !self {
		record["access_requirements"] = cache.Requirements(access)
	}
	if s.Cache != nil {
		if err := s.Cache.Set(ctx, key, record); err != nil && s.Log != nil {
			s.Log.Warn("markdown cache write failed", "error", err)
		}
	}
	return map[string]any{"markdown": document, "generated_at": record["generated_at"], "cached": false}, nil
}
