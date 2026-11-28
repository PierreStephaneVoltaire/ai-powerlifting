package service

import (
	"context"

	"powerlifting/sessions/internal/apperr"
	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/value"
)

const (
	defaultLimit = 50
	maxLimit     = 200
)

func text(arguments map[string]any, key string) string {
	v, _ := arguments[key].(string)
	return v
}

func object(arguments map[string]any, key string) map[string]any {
	v, _ := arguments[key].(map[string]any)
	if v == nil {
		return map[string]any{}
	}
	return v
}

func selector(arguments map[string]any, withIndex bool) session.Selector {
	sel := session.Selector{Date: text(arguments, "date"), SessionID: text(arguments, "session_id")}
	if _, present := arguments["index"]; present && withIndex {
		index := value.IntOf(arguments["index"], 0)
		sel.Index = &index
	}
	return sel
}

func (s *Service) scope(ctx context.Context, arguments map[string]any) (string, session.Scope, error) {
	pk := athleteOf(arguments)
	scope, err := s.sessions.Resolve(ctx, pk)
	return pk, scope, err
}

func rejectIdentity(patch map[string]any) error {
	_, hasID := patch["id"]
	_, hasSessionID := patch["session_id"]
	if hasID || hasSessionID {
		return apperr.Validation("Session identity cannot be changed")
	}
	return nil
}

func (s *Service) create(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	return s.sessions.Create(ctx, pk, scope, object(arguments, "session"))
}

func (s *Service) remove(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	return s.sessions.Delete(ctx, pk, scope, selector(arguments, true))
}

func (s *Service) get(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	return s.sessions.Get(ctx, pk, scope, selector(arguments, true))
}

func (s *Service) list(ctx context.Context, arguments map[string]any) (any, error) {
	limit := defaultLimit
	if raw, present := arguments["limit"]; present {
		limit = value.IntOf(raw, defaultLimit)
	}
	limit = max(1, min(maxLimit, limit))
	return s.sessions.List(ctx, athleteOf(arguments), limit)
}

func (s *Service) listFull(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	return s.sessions.ListFull(ctx, pk, scope)
}

func (s *Service) patch(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	patch := object(arguments, "patch")
	if err := rejectIdentity(patch); err != nil {
		return nil, err
	}
	return s.sessions.Patch(ctx, pk, scope, selector(arguments, true), patch)
}

func (s *Service) patchByDate(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	patch := object(arguments, "patch")
	if err := rejectIdentity(patch); err != nil {
		return nil, err
	}
	return s.sessions.Patch(ctx, pk, scope, selector(arguments, false), patch)
}

func (s *Service) replace(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	replacement := object(arguments, "session")
	sel := selector(arguments, true)
	if sel.SessionID == "" && value.Truthy(replacement["id"]) {
		sel.SessionID = value.Str(replacement["id"])
	}
	return s.sessions.Patch(ctx, pk, scope, sel, replacement)
}

func (s *Service) replaceAll(ctx context.Context, arguments map[string]any) (any, error) {
	pk, scope, err := s.scope(ctx, arguments)
	if err != nil {
		return nil, err
	}
	sessions, _ := arguments["sessions"].([]any)
	if err := s.sessions.ReplaceAll(ctx, pk, scope, sessions); err != nil {
		return nil, err
	}
	return map[string]any{"success": true}, nil
}

func (s *Service) rangeOf(ctx context.Context, arguments map[string]any) (any, error) {
	return s.sessions.Range(ctx, athleteOf(arguments), text(arguments, "start_date"), text(arguments, "end_date"))
}

func (s *Service) exerciseHistory(ctx context.Context, arguments map[string]any) (any, error) {
	return s.sessions.ExerciseHistory(ctx, athleteOf(arguments), text(arguments, "exercise_name"), text(arguments, "exclude_session_id"))
}

func (s *Service) exercisePRs(ctx context.Context, arguments map[string]any) (any, error) {
	return s.sessions.ExercisePRs(ctx, athleteOf(arguments), text(arguments, "exercise_name"))
}
