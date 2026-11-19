package ops

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"

	"powerlifting/program/internal/store"
)

func TestSupplementPhaseCreationAfterBlockTransition(t *testing.T) {
	deps, db := notesDeps(t,
		pointerTo("program#v002"),
		store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{
			"current_block_id": "active",
			"blocks": []any{
				map[string]any{"id": "past", "status": "completed"},
				map[string]any{"id": "active", "status": "active"},
			},
		}, "supplement_phases": []any{map[string]any{"phase": 1, "phase_name": "Past", "items": []any{}}}},
	)
	items := []any{
		map[string]any{"name": "Assessed", "dose": "as recorded", "dose_assessment": "below_range", "questionable_benefits": true, "wada_prohibited": false},
		map[string]any{"name": "Legacy", "dose": "as recorded"},
	}
	phase := map[string]any{"phase": 5, "phase_name": "Off season", "start_week": 1, "end_week": 5, "items": items}
	result, err := supplementPhasesUpdate(deps, notesRequest(map[string]any{"block_id": "active", "phases": []any{phase}}))
	if err != nil {
		t.Fatal(err)
	}
	if phases := result.(map[string]any)["supplement_phases"].([]any); len(phases) != 1 {
		t.Fatalf("approved phase was not returned: %v", result)
	}
	read, err := getSupplements(deps, notesRequest(nil))
	if err != nil || len(read.(map[string]any)["supplement_phases"].([]any)) != 1 {
		t.Fatalf("approved phase is missing on readback: %v, %v", read, err)
	}
	gotItems := read.(map[string]any)["supplement_phases"].([]any)[0].(map[string]any)["items"]
	if !reflect.DeepEqual(gotItems, items) {
		t.Fatalf("optional assessments did not round trip: %v", gotItems)
	}
	stored, err := db.Get(context.Background(), "sup", store.Key{PK: "a1", SK: "program#v002"}, store.GetOptions{})
	if err != nil || len(stored["supplement_phases"].([]any)) != 2 {
		t.Fatalf("past phase must survive alongside the new phase: %v, %v", stored, err)
	}
}

func TestSupplementPhasesRejectPastBlocksWithoutWriting(t *testing.T) {
	for _, target := range []map[string]any{
		{"block_id": "past", "phases": []any{}},
		{"phases": []any{map[string]any{"block_id": "past"}}},
		{"phases": []any{map[string]any{"block": "past"}}},
		{"phases": []any{map[string]any{"block_id": "active", "block": "past"}}},
		{"phases": []any{"invalid"}},
	} {
		original := store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"current_block_id": "active"}, "supplement_phases": []any{map[string]any{"phase": 1, "block_id": "active"}, map[string]any{"phase": 2, "block_id": "past"}}}
		deps, db := notesDeps(t, pointerTo("program#v002"), original)
		before, err := db.Get(context.Background(), "h", store.Key{PK: "a1", SK: "program#v002"}, store.GetOptions{})
		if err != nil {
			t.Fatal(err)
		}
		if _, err := supplementPhasesUpdate(deps, notesRequest(target)); err == nil {
			t.Fatalf("expected validation failure for %v", target)
		}
		stored, err := db.Get(context.Background(), "h", store.Key{PK: "a1", SK: "program#v002"}, store.GetOptions{})
		if err != nil || !reflect.DeepEqual(stored, before) {
			t.Fatalf("rejected write changed data: %v, %v", stored, err)
		}
	}
}

func TestSupplementPhasesReplaceOnlyCurrentBlock(t *testing.T) {
	for _, phases := range [][]any{
		{},
		{map[string]any{"phase": 3, "block_id": "current"}},
		{map[string]any{"phase": 3, "block_id": "active"}},
	} {
		past := map[string]any{"phase": json.Number("1"), "block_id": "past"}
		deps, db := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"current_block_id": "active"}, "supplement_phases": []any{past, map[string]any{"phase": 2, "block_id": "active"}}})
		if _, err := supplementPhasesUpdate(deps, notesRequest(map[string]any{"phases": phases})); err != nil {
			t.Fatal(err)
		}
		stored, err := db.Get(context.Background(), "sup", store.Key{PK: "a1", SK: "program#v002"}, store.GetOptions{})
		if err != nil {
			t.Fatal(err)
		}
		got := stored["supplement_phases"].([]any)
		if len(got) != len(phases)+1 || !reflect.DeepEqual(got[0], past) {
			t.Fatalf("past phases changed: %v", got)
		}
		if len(phases) > 0 && got[1].(map[string]any)["block_id"] != "active" {
			t.Fatalf("new phase is not in the current block: %v", got)
		}
	}
}

func TestCurrentSupplementsExcludeLegacyPreviousBlockItems(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{
		"pk": "a1", "sk": "program#v002",
		"meta": map[string]any{"current_block_id": "active", "blocks": []any{
			map[string]any{"id": "past", "status": "completed"},
			map[string]any{"id": "active", "status": "active"},
		}},
		"supplements":       []any{map[string]any{"name": "Previous protocol"}},
		"supplement_phases": []any{map[string]any{"phase": 1, "phase_name": "Previous phase", "items": []any{}}},
	})
	for _, block := range []string{"current", "past"} {
		result, err := getSupplements(deps, notesRequest(map[string]any{"block_id": block}))
		if err != nil {
			t.Fatal(err)
		}
		want := 0
		if block == "past" {
			want = 1
		}
		for _, field := range []string{"supplements", "supplement_phases"} {
			if got := result.(map[string]any)[field].([]any); len(got) != want {
				t.Fatalf("%s %s contains the wrong block's data: %v", block, field, got)
			}
		}
	}
}
