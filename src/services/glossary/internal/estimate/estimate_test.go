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

var fatigueAnswer = map[string]any{"axial": 0.87, "neural": 0.8, "peripheral": 0.7, "systemic": 0.63, "reasoning": " r "}

func userPrompt(request cache.Request) string {
	return request.Messages[1].(map[string]any)["content"].(string)
}

func TestBatchPromptCarriesAthleteContextOnce(t *testing.T) {
	var seen cache.Request
	athlete := &Athlete{
		Meta:         map[string]any{"height_cm": 182.0, "sex": "", "current_body_weight_kg": 0.0, "body_fat_range": "15_20"},
		LiftProfiles: []map[string]any{{"lift": "deadlift", "options": map[string]any{"stance": "sumo"}, "notes": "tight"}},
	}
	request := Request{
		Athlete: athlete, CurrentMaxes: map[string]any{"deadlift": 300.0},
		Subjects: []Subject{
			{ID: "a", Item: exercise.Item{"name": "Sumo Deadlift", "category": "deadlift"}, Aspects: []string{AspectFatigue, AspectE1RM}, History: []map[string]any{{"kg": 200.0}}},
			{ID: "b", Item: exercise.Item{"name": "Curl"}, Aspects: []string{AspectFatigue, AspectE1RM}},
		},
	}
	_, _, err := Batch(context.Background(), answering(map[string]any{"results": []any{}}, &seen), request)
	if err != nil {
		t.Fatal(err)
	}
	user := userPrompt(seen)
	for _, want := range []string{"id: a", "id: b", "Exercise: Sumo Deadlift", "Exercise: Curl", "height_cm: 182", "body_fat_range: 15 to 20%", "Lift profile (deadlift):", "Notes: tight", "Current competition maxes (kg): {\"deadlift\":300}", "Past sets: [{\"kg\":200}]", "Return: fatigue, e1rm"} {
		if !strings.Contains(user, want) {
			t.Errorf("prompt lacks %q:\n%s", want, user)
		}
	}
	for _, once := range []string{"Athlete context:", "height_cm", "Lift profile (deadlift):", "Current competition maxes"} {
		if strings.Count(user, once) != 1 {
			t.Errorf("%q appears %d times", once, strings.Count(user, once))
		}
	}
	if strings.Contains(user, "sex") || strings.Contains(user, "bodyweight") {
		t.Errorf("prompt carries unset context:\n%s", user)
	}
	system := seen.Messages[0].(map[string]any)["content"].(string)
	if !strings.Contains(system, "## fatigue") || !strings.Contains(system, "## e1rm") || strings.Contains(system, "## muscles") {
		t.Errorf("system prompt sections wrong:\n%s", system)
	}
}

func TestGenericBatchHasNoAthleteContext(t *testing.T) {
	var seen cache.Request
	_, _, _ = Batch(context.Background(), answering(map[string]any{"results": []any{}}, &seen), Request{Subjects: []Subject{{ID: "a", Item: exercise.Item{"name": "Curl"}, Aspects: []string{AspectFatigue}}}})
	if strings.Contains(userPrompt(seen), "Athlete context") {
		t.Fatalf("prompt %q", userPrompt(seen))
	}
}

func TestToolSchemaIsLimitedToRequestedAspectsAndIDs(t *testing.T) {
	var seen cache.Request
	_, _, _ = Batch(context.Background(), answering(map[string]any{"results": []any{}}, &seen), Request{Subjects: []Subject{
		{ID: "a", Item: exercise.Item{"name": "Curl"}, Aspects: []string{AspectFatigue}},
		{ID: "b", Item: exercise.Item{"name": "Row"}, Aspects: []string{AspectText}},
	}})
	schema := seen.Tools[0].(map[string]any)["function"].(map[string]any)["parameters"].(map[string]any)["properties"].(map[string]any)["results"].(map[string]any)["items"].(map[string]any)["properties"].(map[string]any)
	if len(schema) != 3 || schema["fatigue"] == nil || schema["text"] == nil || schema["id"].(map[string]any)["enum"].([]any)[1] != "b" {
		t.Fatalf("schema %v", schema)
	}
}

func TestBatchValidatesEachElementIndependently(t *testing.T) {
	var seen cache.Request
	subjects := []Subject{
		{ID: "ok", Item: exercise.Item{"name": "Squat"}, Aspects: []string{AspectFatigue, AspectMuscles, AspectLiftTransfer, AspectText, AspectE1RM}},
		{ID: "partial", Item: exercise.Item{"name": "Row"}, Aspects: []string{AspectFatigue}},
		{ID: "zero", Item: exercise.Item{"name": "Row"}, Aspects: []string{AspectE1RM}},
		{ID: "absent", Item: exercise.Item{"name": "Row"}, Aspects: []string{AspectFatigue}},
	}
	got, failures, err := Batch(context.Background(), answering(map[string]any{"results": []any{
		map[string]any{
			"id": "ok", "fatigue": fatigueAnswer,
			"muscles":       map[string]any{"primary_muscles": []any{"quads", "glutes", "hamstrings", "calves", "core"}, "secondary_muscles": []any{"quads", "Front Delts", "bogus"}, "tertiary_muscles": []any{"glutes", "traps"}, "reasoning": "r"},
			"lift_transfer": map[string]any{"squat": 0.93, "bench": 0.0, "deadlift": 0.2, "reasoning": " same "},
			"text":          map[string]any{"description": "  A  squat\nvariation ", "how_to_perform": "1. Set up", "why_do_it": "Legs"},
			"e1rm":          map[string]any{"e1rm_kg": 180.0, "ratio": 0.9, "primary_lift_used": "squat", "basis": "history", "confidence": "medium"},
		},
		map[string]any{"id": "partial", "fatigue": map[string]any{"axial": 0.5}},
		map[string]any{"id": "zero", "e1rm": map[string]any{"e1rm_kg": 0.0}},
		map[string]any{"id": "stranger", "fatigue": fatigueAnswer},
	}}, &seen), Request{Subjects: subjects})
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || len(failures) != 3 || failures["absent"] != "missing from model response" || failures["partial"] == "" || failures["zero"] == "" {
		t.Fatalf("got %v failures %v", got, failures)
	}
	ok := got["ok"]
	if ok.Fatigue.Profile["axial"] != 0.85 || ok.Fatigue.Profile["systemic"] != 0.65 || ok.Fatigue.Reasoning != "r" {
		t.Fatalf("fatigue %+v", ok.Fatigue)
	}
	if len(ok.Muscles.Primary) != 4 || len(ok.Muscles.Secondary) != 1 || ok.Muscles.Secondary[0] != "front_delts" || len(ok.Muscles.Tertiary) != 1 || ok.Muscles.Tertiary[0] != "traps" {
		t.Fatalf("muscles %+v", ok.Muscles)
	}
	if ok.LiftTransfer["squat"] != 0.95 || ok.LiftTransfer["source"] != "ai" || ok.LiftTransfer["reasoning"] != "same" {
		t.Fatalf("transfer %v", ok.LiftTransfer)
	}
	if ok.Text.Description != "A squat variation" || ok.E1RM.Kg != 180 {
		t.Fatalf("text %+v e1rm %+v", ok.Text, ok.E1RM)
	}
}

func TestNoToolCallIsAnError(t *testing.T) {
	infer := func(context.Context, cache.Request) (map[string]any, error) {
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{}}}}, nil
	}
	if _, _, err := Batch(context.Background(), infer, Request{Subjects: []Subject{{ID: "a", Item: exercise.Item{"name": "Row"}, Aspects: []string{AspectText}}}}); err == nil {
		t.Fatal("missing tool call accepted")
	}
}
