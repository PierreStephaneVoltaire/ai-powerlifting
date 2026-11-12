package service

import (
	"context"
	"fmt"
	"slices"
	"time"

	"powerlifting/analytics-export/internal/apperr"
	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/contract"
	"powerlifting/analytics-export/internal/store"
)

var reserved = []string{"_person_pk", "_access", "_if_job_id"}

type Bundles interface {
	BlockBundle(ctx context.Context, caller auth.Caller, blockKey string) (map[string]any, error)
}

type handler func(ctx context.Context, arguments map[string]any, caller auth.Caller) (map[string]any, error)

type Service struct {
	Registry *contract.Registry
	access   *auth.Access
	bundles  Bundles
	store    store.Store
	now      func() time.Time
	handlers map[string]handler
}

func New(registry *contract.Registry, access *auth.Access, bundles Bundles, objects store.Store, now func() time.Time) (*Service, error) {
	s := &Service{Registry: registry, access: access, bundles: bundles, store: objects, now: now}
	s.handlers = map[string]handler{
		"analytics.export":          s.blockExport,
		"analytics.lifetime_export": s.lifetimeExport,
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
	if !operation.Public && caller.Person == "" {
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
	result, err := s.handlers[name](ctx, scoped, caller)
	if err != nil {
		return nil, err
	}
	if err := operation.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}
