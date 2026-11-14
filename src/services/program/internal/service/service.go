package service

import (
	"context"
	"fmt"
	"slices"

	"powerlifting/program/internal/analysis"
	"powerlifting/program/internal/apperr"
	"powerlifting/program/internal/auth"
	"powerlifting/program/internal/contract"
	"powerlifting/program/internal/ops"
	"powerlifting/program/internal/pyval"
)

var reserved = []string{"_person_pk", "_access", "_if_job_id"}

type Service struct {
	Registry *contract.Registry
	access   *auth.Access
	deps     *ops.Deps
	versions analysis.Versions
	handlers map[string]ops.Handler
}

func New(registry *contract.Registry, access *auth.Access, deps *ops.Deps, versions analysis.Versions) (*Service, error) {
	s := &Service{Registry: registry, access: access, deps: deps, versions: versions, handlers: ops.Registry()}
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
	request := &ops.Request{
		Ctx: ctx, Athlete: caller.Athlete, Person: caller.Person, Args: scoped, Access: access,
		Caller: ops.Caller{Person: caller.Person, Athlete: caller.Athlete, ActiveJob: caller.ActiveJob()},
	}
	result, err := s.handlers[name](s.deps, request)
	if err != nil {
		return nil, err
	}
	result = render(name, result, ops.Access(access))
	if err := operation.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	s.versions.Record(ctx, name, auth.AnalysisAthlete(access))
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}

func render(name string, result any, access ops.Access) any {
	switch name {
	case "program_get", "health_get_diet_notes", "health_get_supplements":
		result = pyval.Coerce(result)
	case "block_transition":
		result = pyval.Stringify(result)
	default:
		result = pyval.Sanitize(result)
	}
	return ops.OperationResult(name, result, access)
}
