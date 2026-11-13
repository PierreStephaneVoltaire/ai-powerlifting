package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"maps"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/pyjson"
	"powerlifting/analytics-ai/internal/reports"
)

const comparisonSchemaVersion = 6

func (s *Service) inner(call request, name string, arguments map[string]any) (request, error) {
	operation, found := s.Registry.Get(name)
	if !found {
		return request{}, apperr.UnknownOperation()
	}
	if err := operation.ValidateInput(arguments); err != nil {
		return request{}, apperr.Validation(err.Error())
	}
	call = call.clone()
	call.operation, call.arguments = operation, arguments
	return call, nil
}

func (s *Service) wrapper(ctx context.Context, call request) (any, error) {
	switch call.operation.Name {
	case "analytics.block_evaluation":
		return s.blockReport(ctx, call, "block_program_evaluation")
	case "analytics.correlation":
		return s.blockReport(ctx, call, "block_correlation_analysis")
	case "analytics.compare_ai":
		return s.compareReport(ctx, call)
	}
	return nil, apperr.UnknownOperation()
}

func (s *Service) blockReport(ctx context.Context, call request, target string) (any, error) {
	blockKey, _ := call.arguments["blockKey"].(string)
	blocks, err := s.Source.Blocks(ctx, call.principal())
	if err != nil {
		return nil, err
	}
	entry, found := reports.FindBlock(blocks, blockKey)
	if !found {
		return nil, apperr.NotFound("Block %s not found", blockKey)
	}
	if !reports.Sufficient(entry.WeekCount) {
		if target == "block_correlation_analysis" {
			return reports.InsufficientCorrelation(entry.Start, entry.WeekCount, entry.WeekCount), nil
		}
		return reports.InsufficientEvaluation(entry.Start, entry.WeekCount), nil
	}
	arguments := map[string]any{"pk": call.caller.Athlete, "block_key": blockKey, "refresh": truthy(call.arguments["refresh"]), "cache_only": truthy(call.arguments["cacheOnly"])}
	delegated, err := s.inner(call, target, arguments)
	if err != nil {
		return nil, err
	}
	return s.submit(ctx, delegated)
}

func (s *Service) compareReport(ctx context.Context, call request) (any, error) {
	refresh, cacheOnly := truthy(call.arguments["refresh"]), truthy(call.arguments["cacheOnly"])
	if truthy(call.arguments["read_only"]) {
		refresh, cacheOnly = false, true
	}
	var requested []string
	rawKeys, _ := call.arguments["blockKeys"].([]any)
	for _, key := range rawKeys {
		if text, ok := key.(string); ok {
			requested = append(requested, text)
		}
	}
	blocks, err := s.Source.Blocks(ctx, call.principal())
	if err != nil {
		return nil, err
	}
	resolved := reports.ResolveKeys(blocks, requested)
	keys := make([]any, 0, len(resolved))
	for _, key := range resolved {
		keys = append(keys, key)
	}
	comparison, err := s.Source.Compare(ctx, call.principal(), resolved)
	if err != nil {
		return nil, err
	}
	delegated, err := s.inner(call, "multi_block_comparison_analysis", map[string]any{"pk": call.caller.Athlete, "block_keys": keys, "refresh": refresh, "cache_only": cacheOnly})
	if err != nil {
		return nil, err
	}
	summary, err := s.submit(ctx, delegated)
	if err != nil {
		return nil, err
	}
	fingerprint, err := pyjson.Encode(reports.StripMarkers(comparison))
	if err != nil {
		return nil, apperr.Internal(err.Error())
	}
	sum := sha256.Sum256(fingerprint)
	selected, _ := comparison["selectedBlockKeys"].([]any)
	deterministic := comparison
	if len(resolved) > 0 {
		if lifetime, err := s.Source.SelectedLifetime(ctx, call.principal(), resolved); err == nil {
			deterministic = maps.Clone(comparison)
			deterministic["lifetime"] = lifetime
		}
	}
	cached := false
	if object, isObject := summary.(map[string]any); isObject {
		cached = object["cached"] == true
	}
	return map[string]any{
		"schemaVersion": comparisonSchemaVersion, "generatedAt": s.Now().UTC().Format("2006-01-02T15:04:05.000Z"), "cached": cached,
		"selectedBlockKeys": selected, "sourceFingerprint": hex.EncodeToString(sum[:]), "report": summary, "deterministic": deterministic,
	}, nil
}
