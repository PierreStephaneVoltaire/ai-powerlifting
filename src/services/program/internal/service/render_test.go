package service

import (
	"encoding/json"
	"testing"

	"powerlifting/program/internal/ops"
)

func TestBlockTransitionRendersNumbersAsJSONNumbers(t *testing.T) {
	result := map[string]any{
		"action": "complete",
		"program": map[string]any{
			"meta":          map[string]any{"target_squat_kg": json.Number("180"), "target_bench_kg": json.Number("117.5"), "offset": json.Number("-2.5")},
			"current_maxes": map[string]any{"squat": json.Number("180")},
			"phases":        []any{map[string]any{"start_week": json.Number("1")}},
		},
	}
	encoded, err := json.Marshal(render("block_transition", result, ops.Access{"is_self": true}))
	if err != nil {
		t.Fatal(err)
	}
	want := `{"action":"complete","program":{"current_maxes":{"squat":180},"meta":{"offset":-2.5,"target_bench_kg":117.5,"target_squat_kg":180},"phases":[{"start_week":1}]}}`
	if string(encoded) != want {
		t.Fatalf("got  %s\nwant %s", encoded, want)
	}
}
