package estimate

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"powerlifting/glossary/internal/cache"
	"powerlifting/glossary/internal/exercise"
)

func answering(arguments map[string]any, seen *cache.Request) func(context.Context, cache.Request) (map[string]any, error) {
	return func(_ context.Context, request cache.Request) (map[string]any, error) {
		*seen = request
		encoded, _ := json.Marshal(arguments)
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{"tool_calls": []any{map[string]any{"function": map[string]any{"arguments": string(encoded)}}}}}}}, nil
	}
}

func TestFatiguePromptIncludesOnlyKnownAthleteContext(t *testing.T) {
	var seen cache.Request
	athlete := &Athlete{
		Meta:         map[string]any{"height_cm": 182.0, "sex": "", "current_body_weight_kg": 0.0, "body_fat_range": "15_20"},
		LiftProfiles: []map[string]any{{"lift": "deadlift", "options": map[string]any{"stance": "sumo"}, "notes": "tight"}, {"lift": "squat"}},
	}
	got, err := EstimateFatigue(context.Background(), answering(map[string]any{"axial": 0.87, "neural": 0.8, "peripheral": 0.7, "systemic": 0.63, "reasoning": " r "}, &seen), exercise.Item{"name": "Sumo Deadlift", "category": "deadlift"}, athlete)
	if err != nil {
		t.Fatal(err)
	}
	user := seen.Messages[1].(map[string]any)["content"].(string)
	for _, want := range []string{"Exercise: Sumo Deadlift", "Category: deadlift", "height_cm: 182", "body_fat_range: 15 to 20%", "Lift profile (deadlift):", "Volume tolerance: moderate", "Notes: tight"} {
		if !strings.Contains(user, want) {
			t.Errorf("prompt lacks %q:\n%s", want, user)
		}
	}
	if strings.Contains(user, "sex") || strings.Contains(user, "bodyweight") || strings.Contains(user, "Lift profile (squat)") {
		t.Errorf("prompt carries unset or unrelated context:\n%s", user)
	}
	if got.Profile["axial"] != 0.85 || got.Profile["systemic"] != 0.65 || got.Reasoning != "r" {
		t.Fatalf("fatigue %+v", got)
	}
}

func TestGenericFatiguePromptHasNoAthleteContext(t *testing.T) {
	var seen cache.Request
	_, _ = EstimateFatigue(context.Background(), answering(map[string]any{"axial": 0.1, "neural": 0.1, "peripheral": 0.1, "systemic": 0.1, "reasoning": ""}, &seen), exercise.Item{"name": "Curl"}, nil)
	user := seen.Messages[1].(map[string]any)["content"].(string)
	if user != "Exercise: Curl" {
		t.Fatalf("prompt %q", user)
	}
}

func TestMuscleBucketsAreDeduplicatedAndCapped(t *testing.T) {
	var seen cache.Request
	got, err := EstimateMuscles(context.Background(), answering(map[string]any{
		"primary_muscles":   []any{"quads", "glutes", "hamstrings", "calves", "core"},
		"secondary_muscles": []any{"quads", "Front Delts", "bogus"},
		"tertiary_muscles":  []any{"glutes", "traps"},
		"reasoning":         "r",
	}, &seen), exercise.Item{"name": "Squat", "primary_muscles": []any{"quads"}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Primary) != 4 || len(got.Secondary) != 1 || got.Secondary[0] != "front_delts" || len(got.Tertiary) != 1 || got.Tertiary[0] != "traps" {
		t.Fatalf("muscles %+v", got)
	}
	if user := seen.Messages[1].(map[string]any)["content"].(string); !strings.Contains(user, "Existing primary muscles: quads") {
		t.Fatalf("prompt %q", user)
	}
}

func TestE1RMRejectsUnusableAnswer(t *testing.T) {
	var seen cache.Request
	_, err := EstimateE1RM(context.Background(), answering(map[string]any{"estimates": []any{map[string]any{"e1rm_kg": 0.0}}}, &seen), exercise.Item{"name": "Row"}, nil, nil, nil)
	if err == nil {
		t.Fatal("zero e1rm accepted")
	}
}

func TestNoToolCallIsAnError(t *testing.T) {
	infer := func(context.Context, cache.Request) (map[string]any, error) {
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{}}}}, nil
	}
	if _, err := GenerateText(context.Background(), infer, exercise.Item{"name": "Row"}, Athlete{}); err == nil {
		t.Fatal("missing tool call accepted")
	}
}
