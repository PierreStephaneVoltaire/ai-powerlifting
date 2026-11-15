package service

import (
	"context"
	"fmt"
	"log/slog"
	"slices"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/auth"
	"powerlifting/competition/internal/contract"
	"powerlifting/competition/internal/entries"
	"powerlifting/competition/internal/store"
)

var reserved = []string{"_person_pk", "_access", "_if_job_id"}

var analysisInputWrites = map[string]bool{
	"health_update_user_competition":   true,
	"health_complete_user_competition": true,
}

func mutatesCompetition(name string, arguments map[string]any) bool {
	if analysisInputWrites[name] {
		return true
	}
	if name != "health_list_competitions" {
		return false
	}
	operation := competitionOperation(arguments)
	return operation == "update" || operation == "complete"
}

type Accessor interface {
	Fetch(ctx context.Context, operation string, arguments map[string]any, caller auth.Caller) (map[string]any, error)
}

type handler func(ctx context.Context, arguments map[string]any) (any, error)

type Service struct {
	Registry *contract.Registry
	Access   Accessor
	Entries  store.Entries
	Programs store.Programs
	Versions store.AnalysisVersions
	Now      func() time.Time
	Today    func() time.Time
	Log      *slog.Logger
	rows     entries.Service
	handlers map[string]handler
}

func New(registry *contract.Registry, access Accessor, rows store.Entries, programs store.Programs, versions store.AnalysisVersions, now func() time.Time, log *slog.Logger) (*Service, error) {
	s := &Service{
		Registry: registry, Access: access, Entries: rows, Programs: programs, Versions: versions,
		Now: now, Today: now, Log: log,
		rows: entries.Service{Entries: rows, Programs: programs, Now: now},
	}
	s.handlers = map[string]handler{
		"calculate_attempts":                     s.calculateAttempts,
		"health_list_competitions":               s.competitions,
		"health_update_user_competition":         s.competitions,
		"health_complete_user_competition":       s.competitions,
		"health_snapshot_competition_projection": s.snapshot,
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
	access, err := s.Access.Fetch(ctx, name, arguments, caller)
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
	result = visibleResult(name, result, access)
	if err := operation.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	s.recordWrite(ctx, name, scoped, access)
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}

func (s *Service) recordWrite(ctx context.Context, name string, arguments, access map[string]any) {
	athlete := auth.AnalysisAthlete(access)
	if athlete == "" || !mutatesCompetition(name, arguments) {
		return
	}
	if err := s.Versions.Bump(ctx, athlete); err != nil {
		s.Log.Error("analysis version bump failed", "athlete", athlete, "error", err)
	}
}

func pk(arguments map[string]any) string {
	value, _ := arguments["pk"].(string)
	return value
}
