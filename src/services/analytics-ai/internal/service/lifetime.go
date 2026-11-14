package service

import (
	"context"
	"log/slog"
	"slices"
	"time"

	"powerlifting/analytics-ai/internal/data"
	"powerlifting/analytics-ai/internal/reports"
)

const exportTimeout = 60 * time.Second

func (s *Service) allStoredPast(ctx context.Context, call request, selected []string) ([]string, bool) {
	blocks, err := s.Source.Blocks(ctx, call.principal())
	if err != nil {
		return nil, false
	}
	var past []string
	for _, key := range selected {
		if entry, found := reports.FindBlock(blocks, key); found && !entry.Current {
			past = append(past, key)
		}
	}
	stored := reports.ResolveKeys(blocks, nil)
	slices.Sort(past)
	slices.Sort(stored)
	return past, len(past) > 0 && slices.Equal(past, stored)
}

func (s *Service) saveLifetime(ctx context.Context, call request, narrative any, selected []string) {
	body, _ := narrative.(map[string]any)
	if body == nil || body["insufficient_data"] == true || s.Exporter == nil {
		return
	}
	ctx, cancel := context.WithTimeout(ctx, exportTimeout)
	defer cancel()
	blockKeys, all := s.allStoredPast(ctx, call, selected)
	if !all {
		return
	}
	lifetime, err := s.Source.SelectedLifetime(ctx, call.principal(), blockKeys)
	if err != nil {
		slog.Warn("lifetime report unavailable for export", "athlete", call.caller.Athlete, "error", err)
		return
	}
	err = s.Exporter.SaveLifetimeReport(ctx, call.principal(), data.LifetimeReport{
		GeneratedAt: s.Now().UTC().Format("2006-01-02T15:04:05.000Z"), BlockKeys: blockKeys, Report: lifetime, Narrative: body,
	})
	if err != nil {
		slog.Warn("lifetime report export failed", "athlete", call.caller.Athlete, "error", err)
	}
}
