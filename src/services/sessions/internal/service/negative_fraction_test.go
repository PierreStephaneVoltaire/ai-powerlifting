package service

import (
	"encoding/json"
	"strings"
	"testing"

	"powerlifting/sessions/internal/value"
)

func TestSessionGetKeepsNegativeFractions(t *testing.T) {
	h := newHarness(t, map[string]any{"is_self": true, "permissions": []any{}})
	h.memory.SeedHealth(value.Item{"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001", "version": json.Number("1")})
	h.memory.SeedHealth(value.Item{"pk": "athlete", "sk": "program#v001", "meta": map[string]any{}, "phases": []any{}})
	h.memory.SeedSession(value.Item{
		"pk": "athlete", "sk": "session#program#v001#2026-09-14#001#s-a", "id": "s-a", "date": "2026-09-14", "week_number": json.Number("1"),
		"same_day_ordinal": json.Number("1"), "body_weight_delta_kg": json.Number("-2.5"), "status": "planned",
		"exercises": []any{map[string]any{"name": "Squat", "kg": json.Number("-0.75"), "reps": json.Number("5")}},
	})
	result, err := h.call("session_get", map[string]any{"date": "2026-09-14", "index": 0})
	if err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(value.Render(result))
	for _, fragment := range []string{`"body_weight_delta_kg":-2.5`, `"kg":-0.75`, `"reps":5`} {
		if !strings.Contains(string(encoded), fragment) {
			t.Fatalf("missing %s in %s", fragment, encoded)
		}
	}
}
