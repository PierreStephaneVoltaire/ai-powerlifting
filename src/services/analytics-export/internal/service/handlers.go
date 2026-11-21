package service

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"

	"powerlifting/analytics-export/internal/apperr"
	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/data"
	"powerlifting/analytics-export/internal/render"
	"powerlifting/analytics-export/internal/store"
)

const currentBlockKey = "current"

func hasPermission(access map[string]any, permission string) bool {
	return containsPermission(access["permissions"], permission)
}

func containsPermission(raw any, permission string) bool {
	permissions, _ := raw.([]any)
	for _, value := range permissions {
		if value == permission {
			return true
		}
	}
	return false
}

func permittedSessions(raw any, includeBodyweight bool) []map[string]any {
	sessions, _ := raw.([]map[string]any)
	result := make([]map[string]any, 0, len(sessions))
	for _, session := range sessions {
		copy := make(map[string]any, len(session))
		for key, value := range session {
			if !includeBodyweight && (key == "body_weight_kg" || key == "body_weight_lb") {
				continue
			}
			copy[key] = value
		}
		result = append(result, copy)
	}
	return result
}

func envelope(content []byte, contentType, filename string) map[string]any {
	return map[string]any{
		"content_base64":      base64.StdEncoding.EncodeToString(content),
		"content_type":        contentType,
		"content_disposition": fmt.Sprintf(`attachment; filename="%s"`, filename),
	}
}

func (s *Service) blockExport(ctx context.Context, arguments map[string]any, caller auth.Caller, access map[string]any) (map[string]any, error) {
	blockKey, _ := arguments["blockKey"].(string)
	format, _ := arguments["format"].(string)
	if format != "xlsx" && format != "markdown" {
		return nil, apperr.BadRequest("Unsupported export format. Use xlsx or markdown.")
	}
	if blockKey == currentBlockKey {
		return nil, apperr.BadRequest("Use the existing current-block program export for current analysis.")
	}
	bundle, err := s.bundles.BlockBundle(ctx, caller, blockKey)
	if errors.Is(err, data.ErrNotFound) {
		return nil, notFoundBundle(blockKey)
	}
	if err != nil {
		return nil, apperr.Upstream("Block analysis export error: " + err.Error())
	}
	if len(bundle) == 0 {
		return nil, notFoundBundle(blockKey)
	}
	if render.BlockIsCurrent(bundle) {
		return nil, apperr.BadRequest("Use the existing current-block program export for current analysis.")
	}
	for _, key := range []string{"sessions", "weightLog", "dietNotes", "measurements", "liftProfiles", "athleteSex"} {
		delete(bundle, key)
	}
	bundle["athleteSex"] = access["athlete_sex"]
	if snapshot, err := s.bundles.Snapshot(ctx, caller); err == nil {
		isSelf, _ := access["is_self"].(bool)
		if hasPermission(access, "sessions:read") && (isSelf || containsPermission(access["granted_permissions"], "sessions:read")) {
			bundle["sessions"] = permittedSessions(snapshot["sessions"], hasPermission(access, "weight-log:read"))
		}
		if hasPermission(access, "weight-log:read") {
			bundle["weightLog"] = snapshot["weightLog"]
		}
		program, _ := snapshot["program"].(map[string]any)
		if hasPermission(access, "program:read") {
			bundle["dietNotes"], bundle["measurements"] = program["diet_notes"], program["meta"]
		}
		if hasPermission(access, "lift-profiles:read") {
			bundle["liftProfiles"] = program["lift_profiles"]
		}
	}
	if s.ai != nil {
		if evaluation, err := s.ai.BlockEvaluation(ctx, blockKey, caller); err == nil && evaluation != nil {
			bundle["programEvaluation"] = evaluation
		}
		if correlation, err := s.ai.BlockCorrelation(ctx, blockKey, caller); err == nil && correlation != nil {
			bundle["correlation"] = correlation
		}
	}
	filename := render.BlockFilename(bundle, format)
	if format == "markdown" {
		return envelope([]byte(render.BlockMarkdown(bundle, s.now())), render.MarkdownType, filename), nil
	}
	content, err := render.BlockWorkbook(bundle)
	if err != nil {
		return nil, apperr.Upstream("Block analysis export error: " + err.Error())
	}
	return envelope(content, render.XLSXType, filename), nil
}

func notFoundBundle(blockKey string) error {
	return apperr.NotFound("No block analysis found for %s. Open or generate the past block analysis before exporting.", blockKey)
}

func (s *Service) lifetimeExport(ctx context.Context, arguments map[string]any, _ auth.Caller, _ map[string]any) (map[string]any, error) {
	athlete, _ := arguments["pk"].(string)
	format, _ := arguments["format"].(string)
	extension, contentType := "md", render.MarkdownType
	if format == "xlsx" {
		extension, contentType = "xlsx", render.XLSXType
	}
	content, err := s.store.Get(ctx, store.LatestKey(athlete, extension))
	if errors.Is(err, store.ErrNotFound) {
		return nil, apperr.NotFound("No saved lifetime report found. Run the lifetime analysis over all past blocks first.")
	}
	if err != nil {
		return nil, apperr.Upstream("Lifetime export error: " + err.Error())
	}
	return envelope(content, contentType, "lifetime-report."+extension), nil
}
