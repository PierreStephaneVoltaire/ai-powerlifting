package service

import (
	"context"
	"testing"

	"powerlifting/competition/internal/store"
)

func TestEffectiveExercisesMergeCatalogAndOverlay(t *testing.T) {
	memory := store.NewMemory()
	memory.Load("glossary", []store.Item{
		{"pk": "CATALOG", "sk": "EXERCISE#a", "name": "Back Squat", "lift_transfer": map[string]any{"squat": 1.0}},
		{"pk": "CATALOG", "sk": "EXERCISE#b", "name": "Hidden Press"},
		{"pk": "CATALOG", "sk": "EXERCISE#c", "name": "Row"},
		{"pk": "ATHLETE#me", "sk": "EXERCISE#a", "name": "My Squat", "archived": true},
		{"pk": "ATHLETE#me", "sk": "EXERCISE#b", "hidden": true},
		{"pk": "ATHLETE#me", "sk": "EXERCISE#custom", "name": "Mine", "custom": true},
		{"pk": "ATHLETE#me", "sk": "EXERCISE#orphan", "name": "Orphan"},
		{"pk": "ATHLETE#other", "sk": "EXERCISE#c", "hidden": true},
	})
	s := &Service{Programs: memory}
	got, err := s.effectiveExercises(context.Background(), "me")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 3 {
		t.Fatalf("%v", got)
	}
	squat := got[0].(map[string]any)
	if squat["name"] != "My Squat" || squat["archived"] != true || squat["lift_transfer"] == nil {
		t.Errorf("%v", squat)
	}
	if got[1].(map[string]any)["name"] != "Row" || got[2].(map[string]any)["name"] != "Mine" {
		t.Errorf("%v", got)
	}
}
