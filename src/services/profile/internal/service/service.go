package service

import (
	"context"
	"fmt"
	"slices"
	"strings"

	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/auth"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/tags"
	"powerlifting/profile/internal/value"
)

var reserved = []string{"_person_pk", "_access", "_if_job_id"}

var analysisInputWrites = []string{
	"settings_update_age_class", "settings_update_athlete_basics", "settings_update_onboarding_profile", "settings_update_profile",
}

type Request struct {
	Name   string
	Args   map[string]any
	Caller auth.Caller
	Access *access.Context
}

func (r *Request) Person() string { return r.Caller.Person }

func (r *Request) PK() string { return text(r.Args, "pk") }

type handler func(ctx context.Context, req *Request) (any, error)

type Deps struct {
	Registry  *contract.Registry
	DB        *store.DB
	Env       clock.Env
	Versions  store.Versions
	Discord   AvatarSource
	Analytics Analytics
	Avatars   AvatarStore
}

type Service struct {
	Registry *contract.Registry
	deps     Deps
	people   *people.Repo
	access   *access.Provider
	checker  *access.Checker
	tags     *tags.Catalog
	handlers map[string]handler
}

func New(deps Deps) (*Service, error) {
	repo := &people.Repo{DB: deps.DB, Env: deps.Env}
	s := &Service{
		Registry: deps.Registry,
		deps:     deps,
		people:   repo,
		access:   &access.Provider{People: repo, DB: deps.DB, Now: deps.Env.Now},
		tags:     &tags.Catalog{DB: deps.DB, People: repo, Env: deps.Env},
	}
	s.checker = &access.Checker{Rules: deps.Registry.Rule, DB: deps.DB, Backend: func(source string) bool { return auth.Caller{Source: source}.IsBackend() }}
	s.handlers = map[string]handler{}
	s.registerAccess()
	s.registerIdentity()
	s.registerSettings()
	s.registerTags()
	s.registerViews()
	s.registerGrants()
	s.registerRelationships()
	s.registerHandlerContext()
	for _, operation := range deps.Registry.All() {
		if s.handlers[operation.Name] == nil {
			return nil, fmt.Errorf("no handler for %s", operation.Name)
		}
	}
	return s, nil
}

func (s *Service) Call(ctx context.Context, name string, arguments map[string]any, caller auth.Caller) (any, error) {
	operation, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
	}
	for key := range arguments {
		if slices.Contains(reserved, key) {
			return nil, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	granted, err := s.access.Context(ctx, caller.Person, caller.Athlete)
	if err != nil {
		return nil, apperr.Internal(err.Error())
	}
	claims := access.Claims{Athlete: caller.Athlete, Source: caller.Source}
	if err := s.checker.Check(ctx, name, arguments, claims, granted); err != nil {
		return nil, asError(err)
	}
	if name == "access_context" {
		if nested, _ := arguments["operation"].(string); nested != "" {
			inner, _ := arguments["arguments"].(map[string]any)
			if inner == nil {
				inner = map[string]any{}
			}
			if err := s.checker.Check(ctx, nested, inner, claims, granted); err != nil {
				return nil, asError(err)
			}
		}
	}
	scoped, err := auth.Scope(operation, arguments, caller, auth.Who{
		SettingsPK:   granted.SettingsPK,
		OwnAthletePK: granted.OwnAthletePK,
		Operator:     granted.Has("operator:write"),
	})
	if err != nil {
		return nil, err
	}
	if err := operation.ValidateInput(scoped); err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if caller.Nested && caller.ActiveJob() == "" {
		return nil, apperr.NestedWithoutExecution()
	}
	if !caller.Nested && caller.ActiveJob() != "" && caller.Person == "" {
		return nil, apperr.Unauthorized("Verified acting Person required")
	}
	result, err := s.handlers[name](ctx, &Request{Name: name, Args: scoped, Caller: caller, Access: granted})
	if err != nil {
		return nil, asError(err)
	}
	result, err = s.finish(ctx, name, result)
	if err != nil {
		return nil, asError(err)
	}
	result = value.Render(result)
	if err := operation.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if slices.Contains(analysisInputWrites, name) {
		s.deps.Versions.Bump(ctx, auth.AnalysisAthlete(granted.Map()))
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}

func (s *Service) finish(ctx context.Context, name string, result any) (any, error) {
	object, ok := result.(map[string]any)
	if !ok {
		return result, nil
	}
	if strings.HasPrefix(name, "settings_") {
		if raw, present := object["tags"]; present {
			selected, err := s.tags.Selected(ctx, raw, nil)
			if err != nil {
				return nil, err
			}
			object["tags"] = selected.Maps()
		}
	}
	if name == "identity_resolve" {
		settings, _ := object["settings"].(map[string]any)
		selected, err := s.tags.Selected(ctx, settings["tags"], nil)
		if err != nil {
			return nil, err
		}
		settings["tags"] = selected.Maps()
	}
	return object, nil
}

func asError(err error) error {
	if _, ok := err.(*apperr.Error); ok {
		return err
	}
	return apperr.Internal(err.Error())
}

func text(arguments map[string]any, key string) string {
	v, _ := arguments[key].(string)
	return v
}

func object(arguments map[string]any, key string) map[string]any {
	v, _ := arguments[key].(map[string]any)
	return v
}
