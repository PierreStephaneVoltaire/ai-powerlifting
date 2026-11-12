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

func envelope(content []byte, contentType, filename string) map[string]any {
	return map[string]any{
		"content_base64":      base64.StdEncoding.EncodeToString(content),
		"content_type":        contentType,
		"content_disposition": fmt.Sprintf(`attachment; filename="%s"`, filename),
	}
}

func (s *Service) blockExport(ctx context.Context, arguments map[string]any, caller auth.Caller) (map[string]any, error) {
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

func (s *Service) lifetimeExport(ctx context.Context, arguments map[string]any, _ auth.Caller) (map[string]any, error) {
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
