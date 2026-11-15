package service

import (
	"context"
	"slices"
	"strings"

	"powerlifting/glossary/internal/apperr"
	"powerlifting/glossary/internal/exercise"
	"powerlifting/glossary/internal/store"
)

type item = exercise.Item

type entry struct {
	id        string
	catalog   item
	overlay   item
	effective item
}

func (e *entry) hidden() bool {
	hidden, _ := e.overlay["hidden"].(bool)
	return hidden
}

func (s *Service) entries(ctx context.Context, athlete string) ([]*entry, error) {
	catalog, err := s.Store.List(ctx, store.CatalogPK)
	if err != nil {
		return nil, err
	}
	overlays, err := s.Store.List(ctx, store.AthletePK(athlete))
	if err != nil {
		return nil, err
	}
	byID := map[string]*entry{}
	var entries []*entry
	for _, shared := range catalog {
		id := exercise.Text(shared, "id")
		current := &entry{id: id, catalog: shared}
		byID[id] = current
		entries = append(entries, current)
	}
	for _, personal := range overlays {
		id := exercise.Text(personal, "id")
		current, shared := byID[id]
		if !shared {
			if custom, _ := personal["custom"].(bool); !custom {
				continue
			}
			current = &entry{id: id}
			entries = append(entries, current)
		}
		current.overlay = personal
	}
	for _, current := range entries {
		current.effective = exercise.Merge(current.catalog, current.overlay)
	}
	slices.SortFunc(entries, func(a, b *entry) int {
		return strings.Compare(exercise.NameKey(exercise.Text(a.effective, "name")), exercise.NameKey(exercise.Text(b.effective, "name")))
	})
	return entries, nil
}

func (s *Service) load(ctx context.Context, athlete, id string) (*entry, error) {
	catalog, err := s.Store.Get(ctx, store.CatalogKey(id))
	if err != nil {
		return nil, err
	}
	overlay, err := s.Store.Get(ctx, store.OverlayKey(athlete, id))
	if err != nil {
		return nil, err
	}
	if custom, _ := overlay["custom"].(bool); catalog == nil && !custom {
		return nil, apperr.NotFound("Exercise not found: %s", id)
	}
	return &entry{id: id, catalog: catalog, overlay: overlay, effective: exercise.Merge(catalog, overlay)}, nil
}

func (s *Service) list(ctx context.Context, c call) (map[string]any, error) {
	entries, err := s.entries(ctx, c.athlete())
	if err != nil {
		return nil, err
	}
	exercises := make([]any, 0, len(entries))
	updated := ""
	for _, current := range entries {
		for _, source := range []item{current.catalog, current.overlay} {
			updated = max(updated, exercise.Text(source, "updated_at"))
		}
		if !current.hidden() {
			exercises = append(exercises, current.effective)
		}
	}
	if updated == "" {
		updated = s.timestamp()
	}
	return map[string]any{"pk": c.athlete(), "exercises": exercises, "updated_at": updated}, nil
}

func (s *Service) patchOverlay(ctx context.Context, athlete, id string, set item, remove ...string) error {
	set["id"], set["updated_at"] = id, s.timestamp()
	return s.Store.Update(ctx, store.OverlayKey(athlete, id), store.Patch{Set: set, Remove: remove})
}

func (s *Service) upsert(ctx context.Context, c call) (map[string]any, error) {
	payload, _ := c.arguments["exercise"].(map[string]any)
	cleaned := exercise.Clean(payload)
	name, _ := cleaned["name"].(string)
	if name == "" {
		return nil, apperr.Validation("exercise name is required")
	}
	entries, err := s.entries(ctx, c.athlete())
	if err != nil {
		return nil, err
	}
	requested, _ := payload["id"].(string)
	nameKey := exercise.NameKey(name)
	var target, sameName *entry
	for _, current := range entries {
		if current.id == requested {
			target = current
		}
		if sameName == nil && exercise.NameKey(exercise.Text(current.effective, "name")) == nameKey {
			sameName = current
		}
	}
	skipEmpty := false
	switch {
	case target != nil && sameName != nil && sameName.id != target.id:
		return nil, apperr.Conflict("An exercise named " + exercise.Text(sameName.effective, "name") + " already exists")
	case target == nil && sameName != nil:
		target, skipEmpty = sameName, true
	}
	if target == nil {
		return s.createCustom(ctx, c, requested, nameKey, cleaned)
	}
	changed := exercise.Diff(target.effective, cleaned, skipEmpty)
	if _, renamed := changed["name"]; renamed {
		changed["name_key"] = nameKey
	}
	var remove []string
	if target.hidden() {
		remove = append(remove, "hidden")
	}
	if len(changed) > 0 || len(remove) > 0 {
		if err := s.patchOverlay(ctx, c.athlete(), target.id, changed, remove...); err != nil {
			return nil, err
		}
	}
	return map[string]any{"status": "upserted", "id": target.id}, nil
}

func (s *Service) createCustom(ctx context.Context, c call, requested, nameKey string, cleaned item) (map[string]any, error) {
	id := requested
	if id == "" {
		id = newID()
	}
	for _, key := range []string{"primary_muscles", "secondary_muscles", "tertiary_muscles"} {
		if _, present := cleaned[key]; !present {
			cleaned[key] = []any{}
		}
	}
	for _, key := range []string{"description", "how_to_perform", "why_do_it"} {
		if _, present := cleaned[key]; !present {
			cleaned[key] = ""
		}
	}
	if _, present := cleaned["lift_transfer"]; !present {
		cleaned["lift_transfer"] = exercise.RuleLiftTransfer(cleaned)
	}
	if _, present := cleaned["fatigue_profile"]; present && cleaned["fatigue_profile_source"] == nil {
		cleaned["fatigue_profile_source"] = "manual"
	}
	cleaned["name_key"], cleaned["custom"] = nameKey, true
	cleaned["created_by"], cleaned["created_by_person"] = c.athlete(), c.caller.Person
	cleaned["created_at"] = s.timestamp()
	if err := s.patchOverlay(ctx, c.athlete(), id, cleaned); err != nil {
		return nil, err
	}
	return map[string]any{"status": "upserted", "id": id}, nil
}

func (s *Service) archive(archived bool) handler {
	status := "unarchived"
	if archived {
		status = "archived"
	}
	return func(ctx context.Context, c call) (map[string]any, error) {
		id := c.text("id")
		if _, err := s.load(ctx, c.athlete(), id); err != nil {
			return nil, err
		}
		if err := s.patchOverlay(ctx, c.athlete(), id, item{"archived": archived}); err != nil {
			return nil, err
		}
		return map[string]any{"status": status, "id": id}, nil
	}
}

func (s *Service) remove(ctx context.Context, c call) (map[string]any, error) {
	id := c.text("id")
	if _, err := s.load(ctx, c.athlete(), id); err != nil {
		return nil, err
	}
	if err := s.patchOverlay(ctx, c.athlete(), id, item{"hidden": true}); err != nil {
		return nil, err
	}
	return map[string]any{"status": "removed", "id": id}, nil
}

func (s *Service) setE1RM(ctx context.Context, c call) (map[string]any, error) {
	id := c.text("id")
	if _, err := s.load(ctx, c.athlete(), id); err != nil {
		return nil, err
	}
	method := c.text("method")
	if method == "" {
		method = "manual"
	}
	value, _ := c.arguments["value_kg"].(float64)
	manual := method == "manual"
	confidence, basis := "low", ""
	if manual {
		confidence, basis = "medium", "Manual entry"
	}
	estimate := item{"value_kg": value, "method": method, "basis": basis, "confidence": confidence, "set_at": s.timestamp(), "manually_overridden": manual}
	if err := s.patchOverlay(ctx, c.athlete(), id, item{"e1rm_estimate": estimate}); err != nil {
		return nil, err
	}
	return map[string]any{"status": "e1rm_set", "id": id, "value_kg": value, "method": method}, nil
}
