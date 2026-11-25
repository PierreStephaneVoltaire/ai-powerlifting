package service

import (
	"context"
	"reflect"
	"testing"

	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/profile"
)

func TestSuggestRetainsExistingAndFiltersInvalidSelections(t *testing.T) {
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	result, err := Suggest(defs)(context.Background(), map[string]any{"lift": "bench", "description": "wide grip", "profile": map[string]any{"options": map[string]any{"arch": "max"}}}, func(_ context.Context, request cache.Request) (map[string]any, error) {
		if len(request.Tools) != 1 {
			t.Fatalf("expected tool schema")
		}
		return map[string]any{"choices": []any{map[string]any{"message": map[string]any{"tool_calls": []any{map[string]any{"function": map[string]any{"arguments": `{"grip_width":"wide","arch":null,"touch_point":"invalid"}`}}}}}}}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	got := result.(map[string]any)
	if !reflect.DeepEqual(got["options"], map[string]any{"grip_width": "wide", "arch": "max"}) || !reflect.DeepEqual(got["changed"], []string{"grip_width"}) {
		t.Fatalf("unexpected suggestion: %#v", got)
	}
}
