package service

import (
	"context"
	"log/slog"
	"slices"
	"time"

	"powerlifting/export/internal/apperr"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
	"powerlifting/export/internal/hydration"
)

type Accessor interface {
	Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error)
}
type Storage interface {
	Get(context.Context, string, string) (map[string]any, error)
	Put(context.Context, map[string]any) error
	Competitions(context.Context, string) ([]map[string]any, error)
	Programs(context.Context, string) ([]map[string]any, error)
}
type Versions interface {
	Bump(context.Context, string) error
}
type MarkdownCache interface {
	Version(context.Context, string) (string, error)
	Get(context.Context, string) (map[string]any, error)
	Set(context.Context, string, map[string]any) error
}
type ProgramLoader interface {
	Load(context.Context, string, string, string, string, map[string]any) (*hydration.Loaded, error)
}
type Analytics interface {
	Weekly(context.Context, auth.Caller, map[string]any) (map[string]any, error)
}
type Domain interface {
	Call(context.Context, string, string, auth.Caller, map[string]any) (map[string]any, error)
}
type Service struct {
	Registry  *contract.Registry
	Access    Accessor
	Store     Storage
	Versions  Versions
	Cache     MarkdownCache
	Programs  ProgramLoader
	Analytics Analytics
	Domain    Domain
	Now       func() time.Time
	Log       *slog.Logger
}

func New(registry *contract.Registry, access Accessor, storage Storage, versions Versions, log *slog.Logger) *Service {
	return &Service{Registry: registry, Access: access, Store: storage, Versions: versions, Log: log, Now: time.Now}
}
func (s *Service) Call(ctx context.Context, name string, args map[string]any, caller auth.Caller) (any, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return nil, apperr.GenerationWithoutTurn()
	}
	op, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
	}
	for key := range args {
		if slices.Contains([]string{"_person_pk", "_access", "_if_job_id"}, key) {
			return nil, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	access, err := s.Access.Fetch(ctx, name, args, caller)
	if err != nil {
		return nil, err
	}
	if op.InternalOnly && !caller.IsBackend() {
		return nil, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(op, args, caller, access)
	if err != nil {
		return nil, err
	}
	if err = op.ValidateInput(scoped); err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if caller.Nested && caller.ActiveJob() == "" {
		return nil, apperr.NestedWithoutExecution()
	}
	result, err := s.export(ctx, name, scoped, access, caller)
	if err != nil {
		return nil, err
	}
	if err = op.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}
