package service

import (
	"context"
	"log/slog"
	"time"

	"powerlifting/analytics-ai/internal/data"
)

const exportTimeout = 60 * time.Second

func (s *Service) saveLifetime(ctx context.Context, call request, narrative any, blockKeys []string) {
	body, _ := narrative.(map[string]any)
	if body == nil || body["insufficient_data"] == true || s.Exporter == nil {
		return
	}
	ctx, cancel := context.WithTimeout(ctx, exportTimeout)
	defer cancel()
	lifetime, err := s.Source.Lifetime(ctx, call.principal())
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
