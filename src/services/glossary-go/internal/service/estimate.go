package service

import (
	"context"
	"maps"
	"slices"

	"powerlifting/glossary-go/internal/apperr"
	"powerlifting/glossary-go/internal/athlete"
	"powerlifting/glossary-go/internal/estimate"
	"powerlifting/glossary-go/internal/execution"
	"powerlifting/glossary-go/internal/exercise"
	"powerlifting/glossary-go/internal/store"
)

func asList(values []string) []any {
	list := make([]any, 0, len(values))
	for _, value := range values {
		list = append(list, value)
	}
	return list
}

func (s *Service) context(ctx context.Context, athleteID string) (athlete.Program, *estimate.Athlete, error) {
	program, err := s.Athletes.Program(ctx, athleteID)
	if err != nil {
		return program, nil, err
	}
	return program, &estimate.Athlete{Meta: program.Meta, LiftProfiles: program.LiftProfiles}, nil
}

func (s *Service) ensureGeneric(ctx context.Context, current *entry, c call) (string, item, error) {
	shared := current.catalog
	if shared == nil {
		if _, err := s.Generic.Create(ctx, current.effective, c.athlete(), c.caller.Person); err != nil {
			return "", nil, err
		}
		var err error
		if shared, err = s.Store.Get(ctx, store.CatalogKey(current.id)); err != nil || shared == nil {
			return "", nil, err
		}
	}
	status := exercise.Text(shared, "generic_status")
	if status != exercise.GenericReady && status != exercise.GenericPending {
		if err := s.Generic.Requeue(ctx, current.id); err != nil {
			return "", nil, err
		}
		status = exercise.GenericPending
	}
	generic, _ := shared["fatigue_profile"].(map[string]any)
	return status, generic, nil
}

func (s *Service) planFatigue(ctx context.Context, c call) (plan, error) {
	current, err := s.load(ctx, c.athlete(), c.text("id"))
	if err != nil {
		return plan{}, err
	}
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		_, who, err := s.context(ctx, c.athlete())
		if err != nil {
			return nil, err
		}
		fatigue, err := estimate.EstimateFatigue(ctx, infer, current.effective, who)
		if err != nil {
			return nil, err
		}
		personal := item{
			"fatigue_profile": fatigue.Profile, "fatigue_profile_source": "ai_personal",
			"fatigue_profile_reasoning": fatigue.Reasoning, "estimated_at": s.timestamp(),
		}
		if err := s.patchOverlay(ctx, c.athlete(), current.id, personal); err != nil {
			return nil, err
		}
		status, generic, err := s.ensureGeneric(ctx, current, c)
		if err != nil {
			return nil, err
		}
		result := map[string]any{
			"status": "fatigue_estimated", "id": current.id, "fatigue_profile": fatigue.Profile, "reasoning": fatigue.Reasoning,
			"profile": withReasoning(fatigue.Profile, fatigue.Reasoning),
		}
		if status != "" {
			result["generic_status"] = status
		}
		if generic != nil {
			result["generic_fatigue_profile"] = generic
		}
		return result, nil
	}
	return plan{run: run, finish: s.invalidateAthlete(c)}, nil
}

func withReasoning(profile item, reasoning string) item {
	merged := maps.Clone(profile)
	merged["reasoning"] = reasoning
	return merged
}

func (s *Service) invalidateAthlete(c call) func(context.Context, error) {
	return func(ctx context.Context, err error) {
		if err == nil {
			s.touched(ctx, c.athlete())
		}
	}
}

func (s *Service) writeDefinition(ctx context.Context, c call, current *entry, set item) (shared bool, err error) {
	if current.catalog == nil {
		return false, s.patchOverlay(ctx, c.athlete(), current.id, set)
	}
	set["updated_at"] = s.timestamp()
	if err := s.Store.Update(ctx, store.CatalogKey(current.id), store.Patch{Set: set}); err != nil {
		return true, err
	}
	overridden := slices.DeleteFunc(slices.Collect(maps.Keys(set)), func(key string) bool { _, present := current.overlay[key]; return !present })
	if len(overridden) > 0 {
		err = s.Store.Update(ctx, store.OverlayKey(c.athlete(), current.id), store.Patch{Remove: overridden})
	}
	return true, err
}

func (s *Service) definitionFinish(c call, shared *bool) func(context.Context, error) {
	return func(ctx context.Context, err error) {
		if err != nil {
			return
		}
		s.touched(ctx, c.athlete())
		if *shared {
			s.Cache.InvalidateAllGlossaries(ctx)
		}
	}
}

func (s *Service) planMuscles(ctx context.Context, c call) (plan, error) {
	current, err := s.load(ctx, c.athlete(), c.text("id"))
	if err != nil {
		return plan{}, err
	}
	var shared bool
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		_, who, err := s.context(ctx, c.athlete())
		if err != nil {
			return nil, err
		}
		muscles, err := estimate.EstimateMuscles(ctx, infer, current.effective, who)
		if err != nil {
			return nil, err
		}
		shared, err = s.writeDefinition(ctx, c, current, item{
			"primary_muscles": asList(muscles.Primary), "secondary_muscles": asList(muscles.Secondary), "tertiary_muscles": asList(muscles.Tertiary),
		})
		if err != nil {
			return nil, err
		}
		return map[string]any{
			"status": "muscles_estimated", "id": current.id, "primary_muscles": asList(muscles.Primary),
			"secondary_muscles": asList(muscles.Secondary), "tertiary_muscles": asList(muscles.Tertiary), "reasoning": muscles.Reasoning,
		}, nil
	}
	return plan{run: run, finish: s.definitionFinish(c, &shared)}, nil
}

func (s *Service) planLiftTransfer(ctx context.Context, c call) (plan, error) {
	inline, _ := c.arguments["exercise"].(map[string]any)
	id := c.text("id")
	if id == "" {
		run := func(ctx context.Context, infer execution.Inferer) (any, error) {
			transfer, err := estimate.EstimateLiftTransfer(ctx, infer, inline)
			if err != nil {
				return nil, err
			}
			return map[string]any{"status": "lift_transfer_estimated", "lift_transfer": transfer}, nil
		}
		return plan{run: run}, nil
	}
	current, err := s.load(ctx, c.athlete(), id)
	if err != nil {
		return plan{}, err
	}
	var shared bool
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		subject := maps.Clone(current.effective)
		maps.Copy(subject, inline)
		transfer, err := estimate.EstimateLiftTransfer(ctx, infer, subject)
		if err != nil {
			return nil, err
		}
		if shared, err = s.writeDefinition(ctx, c, current, item{"lift_transfer": transfer}); err != nil {
			return nil, err
		}
		return map[string]any{"status": "lift_transfer_estimated", "id": id, "lift_transfer": transfer}, nil
	}
	return plan{run: run, finish: s.definitionFinish(c, &shared)}, nil
}

func (s *Service) planText(ctx context.Context, c call) (plan, error) {
	subject, _ := c.arguments["exercise"].(map[string]any)
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		var who estimate.Athlete
		if given, present := c.arguments["lift_profiles"].([]any); present {
			for _, profile := range given {
				if object, isObject := profile.(map[string]any); isObject {
					who.LiftProfiles = append(who.LiftProfiles, object)
				}
			}
		} else if program, err := s.Athletes.Program(ctx, c.athlete()); err == nil {
			who.LiftProfiles = program.LiftProfiles
		}
		text, err := estimate.GenerateText(ctx, infer, subject, who)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "generated", "description": text.Description, "how_to_perform": text.HowToPerform, "why_do_it": text.WhyDoIt}, nil
	}
	return plan{run: run}, nil
}

func (s *Service) planE1RM(ctx context.Context, c call) (plan, error) {
	current, err := s.load(ctx, c.athlete(), c.text("id"))
	if err != nil {
		return plan{}, err
	}
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		program, err := s.Athletes.Program(ctx, c.athlete())
		if err != nil {
			return nil, err
		}
		instances, err := s.Athletes.Instances(ctx, c.athlete(), program, exercise.Text(current.effective, "name"))
		if err != nil {
			return nil, err
		}
		estimated, err := estimate.EstimateE1RM(ctx, infer, current.effective, program.CurrentMaxes, program.LiftProfiles, instances)
		if err != nil {
			return nil, err
		}
		stored := item{"value_kg": estimated.Kg, "method": "ai_backfill", "basis": estimated.Basis, "confidence": "low", "set_at": s.timestamp(), "manually_overridden": false}
		if err := s.patchOverlay(ctx, c.athlete(), current.id, item{"e1rm_estimate": stored}); err != nil {
			return nil, err
		}
		return map[string]any{"status": "estimated", "id": current.id, "estimate": map[string]any{
			"e1rm_kg": estimated.Kg, "basis": estimated.Basis, "ratio": estimated.Ratio, "primary_lift_used": estimated.PrimaryLift, "confidence": estimated.Confidence,
		}}, nil
	}
	return plan{run: run, finish: s.invalidateAthlete(c)}, nil
}

func (s *Service) planGeneric(ctx context.Context, c call) (plan, error) {
	id := c.text("id")
	catalog, err := s.Store.Get(ctx, store.CatalogKey(id))
	if err != nil {
		return plan{}, err
	}
	if catalog == nil {
		return plan{}, apperr.NotFound("Catalog exercise not found: %s", id)
	}
	run := func(ctx context.Context, infer execution.Inferer) (any, error) {
		status := exercise.Text(catalog, "generic_status")
		if status != exercise.GenericPending {
			return map[string]any{"status": "skipped", "id": id, "generic_status": status}, nil
		}
		estimated, err := s.estimateGeneric(ctx, infer, catalog)
		if err != nil {
			return nil, err
		}
		if err := s.Generic.Complete(ctx, id, estimated); err != nil {
			return nil, err
		}
		return map[string]any{"status": "generic_estimated", "id": id, "generic_status": exercise.GenericReady}, nil
	}
	finish := func(ctx context.Context, err error) {
		s.Generic.Done(id)
		if err != nil {
			s.Generic.Fail(ctx, id)
			return
		}
		s.Cache.BumpAnalysis(ctx, c.athlete())
		s.Cache.InvalidateAllGlossaries(ctx)
	}
	return plan{run: run, finish: finish}, nil
}

func (s *Service) estimateGeneric(ctx context.Context, infer execution.Inferer, catalog item) (item, error) {
	subject := maps.Clone(catalog)
	estimated := item{}
	if len(exercise.Strings(subject, "primary_muscles")) == 0 {
		muscles, err := estimate.EstimateMuscles(ctx, infer, subject, nil)
		if err != nil {
			return nil, err
		}
		estimated["primary_muscles"], estimated["secondary_muscles"], estimated["tertiary_muscles"] = asList(muscles.Primary), asList(muscles.Secondary), asList(muscles.Tertiary)
		maps.Copy(subject, estimated)
	}
	if exercise.Text(subject, "description") == "" || exercise.Text(subject, "how_to_perform") == "" || exercise.Text(subject, "why_do_it") == "" {
		text, err := estimate.GenerateText(ctx, infer, subject, estimate.Athlete{})
		if err != nil {
			return nil, err
		}
		for key, generated := range map[string]string{"description": text.Description, "how_to_perform": text.HowToPerform, "why_do_it": text.WhyDoIt} {
			if exercise.Text(subject, key) == "" {
				estimated[key], subject[key] = generated, generated
			}
		}
	}
	if existing, _ := subject["lift_transfer"].(map[string]any); exercise.Text(existing, "source") != "user" {
		transfer, err := estimate.EstimateLiftTransfer(ctx, infer, subject)
		if err != nil {
			return nil, err
		}
		estimated["lift_transfer"] = transfer
	}
	fatigue, err := estimate.EstimateFatigue(ctx, infer, subject, nil)
	if err != nil {
		return nil, err
	}
	estimated["fatigue_profile"], estimated["fatigue_profile_source"], estimated["fatigue_profile_reasoning"] = fatigue.Profile, "ai_generic", fatigue.Reasoning
	return estimated, nil
}
