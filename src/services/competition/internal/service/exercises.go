package service

import (
	"context"
	"sort"
	"strings"

	"powerlifting/competition/internal/store"
)

func (s *Service) effectiveExercises(ctx context.Context, athlete string) ([]any, error) {
	catalog, err := s.Programs.GlossaryEntries(ctx, store.GlossaryCatalogPK)
	if err != nil {
		return nil, err
	}
	overlays, err := s.Programs.GlossaryEntries(ctx, store.GlossaryAthletePK+athlete)
	if err != nil {
		return nil, err
	}
	byID := map[string]store.Item{}
	for _, item := range catalog {
		byID[exerciseID(item)] = item
	}
	merged := map[string]store.Item{}
	for id, item := range byID {
		merged[id] = item
	}
	hidden := map[string]bool{}
	for _, overlay := range overlays {
		id := exerciseID(overlay)
		base, shared := byID[id]
		if !shared {
			if custom, _ := overlay["custom"].(bool); !custom {
				continue
			}
		}
		if flag, _ := overlay["hidden"].(bool); flag {
			hidden[id] = true
		}
		merged[id] = mergeExercise(base, overlay)
	}
	ids := make([]string, 0, len(merged))
	for id := range merged {
		if !hidden[id] {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	out := make([]any, len(ids))
	for index, id := range ids {
		out[index] = map[string]any(merged[id])
	}
	return out, nil
}

func exerciseID(item store.Item) string {
	sk, _ := item["sk"].(string)
	return strings.TrimPrefix(sk, store.GlossarySKPrefix)
}

func mergeExercise(catalog, overlay store.Item) store.Item {
	effective := store.Item{}
	for key, value := range catalog {
		effective[key] = value
	}
	delete(effective, "archived")
	for key, value := range overlay {
		effective[key] = value
	}
	return effective
}
