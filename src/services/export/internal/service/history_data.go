package service

import (
	"context"
	"fmt"

	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/scope"
	"powerlifting/export/internal/values"
	"powerlifting/export/internal/workbook"
)

func scopedEntries(raw []any, start, end string) []map[string]any {
	result := []map[string]any{}
	if start == "" || end == "" {
		return result
	}
	for _, value := range raw {
		entry, ok := value.(map[string]any)
		if !ok {
			continue
		}
		date := values.Str2(entry["date"])
		if len(date) > 10 {
			date = date[:10]
		}
		if start <= date && date <= end {
			result = append(result, entry)
		}
	}
	return result
}

func (s *Service) historyData(ctx context.Context, caller auth.Caller, program, access, window map[string]any, sessions []any, block string, version int, start, end string) workbook.Context {
	result := workbook.Context{}
	athlete := caller.Athlete
	if s.Store != nil && hasPermission(access, "federation:read") {
		result.Federations, _ = s.Store.Get(ctx, athlete, "federations#v1")
	}
	if s.Store != nil && version > 0 && hasPermission(access, "weight-log:read") {
		item, err := s.Store.Get(ctx, athlete, fmt.Sprintf("weight_log#v%03d", version))
		if err == nil {
			entries, _ := item["entries"].([]any)
			entries = scope.Entries(entries, scope.Resolve(program, block), program, "weight_log")
			result.WeightLog = scopedEntries(entries, start, end)
		}
	}
	if s.Domain == nil {
		return result
	}
	if version > 0 && hasPermission(access, "performance:read") {
		item, err := s.Domain.Call(ctx, "performance", "max_history_get", caller, map[string]any{"pk": athlete, "version": fmt.Sprintf("v%03d", version)})
		if err == nil {
			entries, _ := item["entries"].([]any)
			result.MaxHistory = scopedEntries(entries, start, end)
		}
	}
	if hasPermission(access, "glossary:read") {
		item, err := s.Domain.Call(ctx, "glossary", "exercise_get_glossary", caller, map[string]any{"pk": athlete})
		if err == nil {
			result.Glossary = values.Maps(item["exercises"])
		}
	}
	sessionBlock := block
	if block == "current" || block == scope.CurrentBlockID(program) {
		sessionBlock = "current"
	}
	for _, operation := range report.CachedReports(sessionBlock, window, sessions, access) {
		item, err := s.Domain.Call(ctx, "analytics-ai", operation, caller, map[string]any{"pk": athlete, "blockKey": "current", "cacheOnly": true, "refresh": false})
		if err != nil || values.Truthy(item["cache_miss"]) {
			continue
		}
		if operation == "analytics.correlation" {
			result.Correlation = item
		} else {
			result.Evaluation = item
		}
	}
	return result
}
