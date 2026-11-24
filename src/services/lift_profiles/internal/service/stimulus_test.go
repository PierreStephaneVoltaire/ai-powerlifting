package service

import (
	"context"
	"strings"
	"testing"

	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/profile"
)

func TestStimulusRequiresAllFieldsAndRoundsResult(t *testing.T) {
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	handler := Stimulus(defs, Programs{})
	_, err = handler(context.Background(), map[string]any{"profile": map[string]any{"lift": "bench"}}, nil)
	if err == nil || !strings.Contains(err.Error(), "Choose every option") {
		t.Fatalf("unexpected error: %v", err)
	}
	options := map[string]any{}
	for _, field := range defs["bench"] {
		options[field.Key] = field.Options[0].Value
	}
	result, err := handler(context.Background(), map[string]any{"profile": map[string]any{"lift": "bench", "options": options}}, func(_ context.Context, request cache.Request) (map[string]any, error) {
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{"tool_calls": []any{map[string]any{"function": map[string]any{"arguments": `{"stimulus_coefficient":1.23,"confidence":"medium","reasoning":"test"}`}}}}}}}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	got := result.(map[string]any)
	if got["stimulus_coefficient"] != 1.25 || got["stimulus_coefficient_confidence"] != "medium" {
		t.Fatalf("unexpected result: %#v", got)
	}
}
