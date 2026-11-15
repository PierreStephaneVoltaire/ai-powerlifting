package service

import (
	"context"
	"errors"
	"maps"
	"slices"
	"strings"

	"powerlifting/glossary/internal/apperr"
	"powerlifting/glossary/internal/estimate"
	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
	"powerlifting/glossary/internal/store"
)

const batchOperation = "glossary_estimate_batch"

func asList(values []string) []any {
	list := make([]any, 0, len(values))
	for _, value := range values {
		list = append(list, value)
	}
	return list
}

func (c call) strings(key string) []string {
	values, _ := c.arguments[key].([]any)
	var unique []string
	for _, value := range values {
		if text, _ := value.(string); text != "" && !slices.Contains(unique, text) {
			unique = append(unique, text)
		}
	}
	return unique
}

func failure(id, reason string) map[string]any {
	return map[string]any{"id": id, "reason": reason}
}

func definitionSet(estimated estimate.Estimate) item {
	set := item{}
	if muscles := estimated.Muscles; muscles != nil {
		set["primary_muscles"], set["secondary_muscles"], set["tertiary_muscles"] = asList(muscles.Primary), asList(muscles.Secondary), asList(muscles.Tertiary)
	}
	if estimated.LiftTransfer != nil {
		set["lift_transfer"] = estimated.LiftTransfer
	}
	if text := estimated.Text; text != nil {
		set["description"], set["how_to_perform"], set["why_do_it"] = text.Description, text.HowToPerform, text.WhyDoIt
	}
	return set
}

func (s *Service) personalSet(estimated estimate.Estimate) item {
	set := item{}
	if fatigue := estimated.Fatigue; fatigue != nil {
		set["fatigue_profile"], set["fatigue_profile_source"] = fatigue.Profile, "ai_personal"
		set["fatigue_profile_reasoning"], set["estimated_at"] = fatigue.Reasoning, s.timestamp()
	}
	if e1rm := estimated.E1RM; e1rm != nil {
		set["e1rm_estimate"] = item{"value_kg": e1rm.Kg, "method": "ai_backfill", "basis": e1rm.Basis, "confidence": "low", "set_at": s.timestamp(), "manually_overridden": false}
	}
	return set
}

func (s *Service) ensureGeneric(ctx context.Context, current *entry, c call) (bool, error) {
	if current.catalog == nil {
		return s.Generic.Create(ctx, current.effective, c.athlete(), c.caller.Person)
	}
	status := exercise.Text(current.catalog, "generic_status")
	if status == exercise.GenericReady || status == exercise.GenericPending {
		return false, nil
	}
	return true, s.Generic.Requeue(ctx, current.id)
}

func (s *Service) saveEstimate(ctx context.Context, c call, current *entry, estimated estimate.Estimate) (catalogChanged bool, err error) {
	definition := definitionSet(estimated)
	personal := s.personalSet(estimated)
	if len(definition) > 0 && current.catalog == nil {
		maps.Copy(personal, definition)
	} else if len(definition) > 0 {
		catalogChanged = true
		set := maps.Clone(definition)
		set["updated_at"] = s.timestamp()
		if err := s.Store.Update(ctx, store.CatalogKey(current.id), store.Patch{Set: set}); err != nil {
			return true, err
		}
		overridden := slices.DeleteFunc(slices.Collect(maps.Keys(definition)), func(key string) bool { _, present := current.overlay[key]; return !present })
		if len(overridden) > 0 {
			if err := s.Store.Update(ctx, store.OverlayKey(c.athlete(), current.id), store.Patch{Remove: overridden}); err != nil {
				return true, err
			}
		}
	}
	if len(personal) > 0 {
		if err := s.patchOverlay(ctx, c.athlete(), current.id, personal); err != nil {
			return catalogChanged, err
		}
	}
	if estimated.Fatigue == nil {
		return catalogChanged, nil
	}
	merged := &entry{id: current.id, catalog: current.catalog, overlay: current.overlay, effective: maps.Clone(current.effective)}
	maps.Copy(merged.effective, definition)
	changed, err := s.ensureGeneric(ctx, merged, c)
	return catalogChanged || changed, err
}

func (s *Service) loadAll(ctx context.Context, athlete string, ids []string) ([]*entry, []any, error) {
	var entries []*entry
	failed := []any{}
	for _, id := range ids {
		current, err := s.load(ctx, athlete, id)
		var app *apperr.Error
		if errors.As(err, &app) && app.Status == 404 {
			failed = append(failed, failure(id, app.Message))
			continue
		}
		if err != nil {
			return nil, nil, err
		}
		entries = append(entries, current)
	}
	if len(entries) == 0 {
		return nil, nil, apperr.NotFound("Exercise not found: %s", strings.Join(ids, ", "))
	}
	return entries, failed, nil
}

func (s *Service) request(ctx context.Context, c call, entries []*entry, aspects []string) (estimate.Request, error) {
	request := estimate.Request{}
	personal := slices.ContainsFunc(aspects, func(aspect string) bool { return aspect != estimate.AspectLiftTransfer })
	if personal {
		loaded, err := s.Athletes.Program(ctx, c.athlete())
		if err != nil {
			return request, err
		}
		request.Athlete = &estimate.Athlete{Meta: loaded.Meta, LiftProfiles: loaded.LiftProfiles}
		request.CurrentMaxes = loaded.CurrentMaxes
		for _, current := range entries {
			subject := estimate.Subject{ID: current.id, Item: current.effective, Aspects: aspects}
			if slices.Contains(aspects, estimate.AspectE1RM) {
				history, err := s.Athletes.Instances(ctx, c.athlete(), loaded, exercise.Text(current.effective, "name"))
				if err != nil {
					return request, err
				}
				subject.History = history
			}
			request.Subjects = append(request.Subjects, subject)
		}
		return request, nil
	}
	for _, current := range entries {
		request.Subjects = append(request.Subjects, estimate.Subject{ID: current.id, Item: current.effective, Aspects: aspects})
	}
	return request, nil
}

func (s *Service) planBatch(ctx context.Context, c call) (plan, error) {
	entries, failed, err := s.loadAll(ctx, c.athlete(), c.strings("ids"))
	if err != nil {
		return plan{}, err
	}
	aspects := c.strings("aspects")
	saved := []any{}
	catalogChanged := false
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		request, err := s.request(ctx, c, entries, aspects)
		if err != nil {
			return nil, err
		}
		estimates, failures, err := estimate.Batch(ctx, infer, request)
		if err != nil {
			return nil, err
		}
		for _, current := range entries {
			if reason, rejected := failures[current.id]; rejected {
				failed = append(failed, failure(current.id, reason))
				continue
			}
			changed, err := s.saveEstimate(ctx, c, current, estimates[current.id])
			catalogChanged = catalogChanged || changed
			if err != nil {
				failed = append(failed, failure(current.id, err.Error()))
				continue
			}
			saved = append(saved, current.id)
		}
		return map[string]any{"saved": saved, "failed": failed}, nil
	}
	finish := func(ctx context.Context, _ error) {
		if len(saved) > 0 {
			s.touched(ctx, c.athlete())
		}
		if catalogChanged {
			s.Cache.InvalidateCatalog(ctx)
		}
	}
	return plan{run: run, finish: finish}, nil
}
