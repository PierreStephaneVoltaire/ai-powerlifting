package service

import (
	"context"
	"fmt"
	"slices"

	"powerlifting/sessions/internal/apperr"
	"powerlifting/sessions/internal/auth"
	"powerlifting/sessions/internal/contract"
	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/store"
	"powerlifting/sessions/internal/value"
)

var reserved = []string{"_person_pk", "_access", "_if_job_id"}

var analysisInputWrites = []string{
	"session_create", "session_delete", "session_patch", "session_patch_by_date", "session_replace", "session_replace_all",
}

type Access interface {
	Fetch(ctx context.Context, operation string, arguments map[string]any, caller auth.Caller) (map[string]any, error)
}

type handler func(ctx context.Context, arguments map[string]any) (any, error)

type Service struct {
	Registry *contract.Registry
	access   Access
	sessions *session.Service
	versions store.Versions
	handlers map[string]handler
}

func New(registry *contract.Registry, access Access, sessions *session.Service, versions store.Versions) (*Service, error) {
	s := &Service{Registry: registry, access: access, sessions: sessions, versions: versions}
	s.handlers = map[string]handler{
		"session_create":            s.create,
		"session_delete":            s.remove,
		"session_get":               s.get,
		"session_list":              s.list,
		"session_list_full":         s.listFull,
		"session_patch":             s.patch,
		"session_patch_by_date":     s.patchByDate,
		"session_replace":           s.replace,
		"session_replace_all":       s.replaceAll,
		"health_get_sessions_range": s.rangeOf,
	}
	for _, operation := range registry.All() {
		if s.handlers[operation.Name] == nil {
			return nil, fmt.Errorf("no handler for %s", operation.Name)
		}
	}
	return s, nil
}

func (s *Service) Call(ctx context.Context, name string, arguments map[string]any, caller auth.Caller) (any, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return nil, apperr.GenerationWithoutTurn()
	}
	operation, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
	}
	for key := range arguments {
		if slices.Contains(reserved, key) {
			return nil, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	if caller.Person == "" {
		return nil, apperr.Forbidden("Authenticated Person required")
	}
	access, err := s.access.Fetch(ctx, name, arguments, caller)
	if err != nil {
		return nil, err
	}
	if operation.InternalOnly && !caller.IsBackend() {
		return nil, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(operation, arguments, caller, access)
	if err != nil {
		return nil, err
	}
	if err := operation.ValidateInput(scoped); err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if caller.Nested && caller.ActiveJob() == "" {
		return nil, apperr.NestedWithoutExecution()
	}
	result, err := s.handlers[name](ctx, scoped)
	if err != nil {
		return nil, err
	}
	result = value.Render(operationResult(name, result, access))
	if err := operation.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if slices.Contains(analysisInputWrites, name) {
		s.versions.Bump(ctx, auth.AnalysisAthlete(access))
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}

func athleteOf(arguments map[string]any) string {
	pk, _ := arguments["pk"].(string)
	return pk
}
