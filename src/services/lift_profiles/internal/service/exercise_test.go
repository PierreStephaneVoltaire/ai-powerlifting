package service

import (
	"context"
	"reflect"
	"testing"

	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/profile"
)

func TestExerciseEstimatesNormalizeResults(t *testing.T) {
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	program := Programs{DB: &programFake{}, Table: "health"}
	args := map[string]any{"pk": "athlete", "exercise": map[string]any{"name": "bench press"}}
	muscles, err := ExerciseEstimate(defs, program, true)(context.Background(), args, func(context.Context, cache.Request) (map[string]any, error) {
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{"tool_calls": []any{map[string]any{"function": map[string]any{"arguments": `{"primary_muscles":["chest","front deltoids"],"secondary_muscles":["chest","triceps"],"tertiary_muscles":[],"reasoning":"press"}`}}}}}}}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := muscles.(map[string]any)["secondary_muscles"]; !reflect.DeepEqual(got, []string{"triceps"}) {
		t.Fatalf("got %#v", got)
	}
	fatigue, err := ExerciseEstimate(defs, program, false)(context.Background(), args, func(context.Context, cache.Request) (map[string]any, error) {
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{"tool_calls": []any{map[string]any{"function": map[string]any{"arguments": `{"axial":0.31,"neural":0.42,"peripheral":0.53,"systemic":0.2,"reasoning":"press"}`}}}}}}}, nil
	})
	if err != nil || fatigue.(map[string]any)["axial"] != 0.3 || fatigue.(map[string]any)["peripheral"] != 0.55 {
		t.Fatalf("got %#v, %v", fatigue, err)
	}
}
