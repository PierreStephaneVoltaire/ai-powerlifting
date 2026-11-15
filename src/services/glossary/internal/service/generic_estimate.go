package service

import (
	"context"
	"slices"

	"powerlifting/glossary/internal/estimate"
	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
	"powerlifting/glossary/internal/store"
)

func genericAspects(catalog item) []string {
	aspects := []string{estimate.AspectFatigue}
	if len(exercise.Strings(catalog, "primary_muscles")) == 0 {
		aspects = append(aspects, estimate.AspectMuscles)
	}
	if exercise.Text(catalog, "description") == "" || exercise.Text(catalog, "how_to_perform") == "" || exercise.Text(catalog, "why_do_it") == "" {
		aspects = append(aspects, estimate.AspectText)
	}
	if existing, _ := catalog["lift_transfer"].(map[string]any); exercise.Text(existing, "source") != "user" {
		aspects = append(aspects, estimate.AspectLiftTransfer)
	}
	return aspects
}

func genericSet(catalog item, estimated estimate.Estimate) item {
	set := definitionSet(estimated)
	for _, key := range []string{"description", "how_to_perform", "why_do_it"} {
		if exercise.Text(catalog, key) != "" {
			delete(set, key)
		}
	}
	if fatigue := estimated.Fatigue; fatigue != nil {
		set["fatigue_profile"], set["fatigue_profile_source"], set["fatigue_profile_reasoning"] = fatigue.Profile, "ai_generic", fatigue.Reasoning
	}
	return set
}

func (s *Service) planGeneric(ctx context.Context, c call) (plan, error) {
	ids := c.strings("ids")
	catalogs := map[string]item{}
	var pending []string
	failed, skipped, saved := []any{}, []any{}, []any{}
	for _, id := range ids {
		catalog, err := s.Store.Get(ctx, store.CatalogKey(id))
		if err != nil {
			return plan{}, err
		}
		switch {
		case catalog == nil:
			failed = append(failed, failure(id, "Catalog exercise not found"))
		case exercise.Text(catalog, "generic_status") != exercise.GenericPending:
			skipped = append(skipped, id)
		default:
			catalogs[id] = catalog
			pending = append(pending, id)
		}
	}
	var rejected []string
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		if len(pending) > 0 {
			request := estimate.Request{}
			for _, id := range pending {
				request.Subjects = append(request.Subjects, estimate.Subject{ID: id, Item: catalogs[id], Aspects: genericAspects(catalogs[id])})
			}
			estimates, failures, err := estimate.Batch(ctx, infer, request)
			if err != nil {
				return nil, err
			}
			for _, id := range pending {
				if reason, bad := failures[id]; bad {
					failed, rejected = append(failed, failure(id, reason)), append(rejected, id)
					continue
				}
				if err := s.Generic.Complete(ctx, id, genericSet(catalogs[id], estimates[id])); err != nil {
					failed, rejected = append(failed, failure(id, err.Error())), append(rejected, id)
					continue
				}
				saved = append(saved, id)
			}
		}
		return map[string]any{"saved": saved, "failed": failed, "skipped": skipped}, nil
	}
	finish := func(ctx context.Context, err error) {
		for _, id := range ids {
			s.Generic.Done(id)
		}
		for _, id := range pending {
			if err != nil || slices.Contains(rejected, id) {
				s.Generic.Fail(ctx, id)
			}
		}
		if err == nil && len(saved) > 0 {
			s.Cache.InvalidateCatalog(ctx)
		}
	}
	return plan{run: run, finish: finish}, nil
}
