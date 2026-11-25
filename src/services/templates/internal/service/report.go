package service

import (
	"context"
	"time"

	"powerlifting/templates/internal/apperr"
	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/metrics"
)

func (s *Service) report(ctx context.Context, sk string, args map[string]any, caller auth.Caller, owners []string) (map[string]any, error) {
	template, err := s.Library.Get(ctx, sk, owners)
	if err != nil {
		return nil, err
	}
	if s.Sources == nil || s.Domain == nil {
		return nil, apperr.Upstream("Sources unavailable")
	}
	pk := value(args["pk"])
	program, err := s.Sources.ProgramContext(ctx, pk)
	if err != nil {
		return nil, apperr.Upstream("Program service unavailable")
	}
	entries, err := s.Sources.Glossary(ctx, pk)
	if err != nil {
		return nil, apperr.Upstream("Glossary service unavailable")
	}
	maxes, _ := program["current_maxes"].(map[string]any)
	profiles, _ := program["lift_profiles"].([]any)
	projected, summary, err := metrics.Program(template, entries, maxes, profiles, time.Now())
	if err != nil {
		return nil, apperr.Validation(err.Error())
	}
	computed := metrics.Result(projected, summary, func(input map[string]any) (map[string]any, error) {
		input["pk"] = pk
		return s.Domain.Call(ctx, "analytics", "weekly_analysis", input, caller)
	})
	meta, _ := template["meta"].(map[string]any)
	context := value(meta["program_context"])
	return map[string]any{"sk": sk, "name": meta["name"], "program_context": context, "evaluation": meta["ai_evaluation"], "metrics": computed}, nil
}
