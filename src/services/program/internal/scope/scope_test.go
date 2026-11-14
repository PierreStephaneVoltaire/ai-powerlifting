package scope

import "testing"

func program() map[string]any {
	return map[string]any{
		"meta": map[string]any{
			"current_block_id": "b2",
			"blocks": []any{
				map[string]any{"id": "b1", "status": "completed", "start_date": "2026-01-05"},
				map[string]any{"id": "b2", "status": "active", "start_date": "2026-06-01"},
			},
		},
		"diet_notes": []any{
			map[string]any{"date": "2026-02-10"},
			map[string]any{"date": "2026-06-10"},
			map[string]any{"block_id": "current"},
			"junk",
		},
	}
}

func TestRecordBlockResolvesByDateThenStamp(t *testing.T) {
	p := program()
	if got := RecordBlock(map[string]any{"date": "2026-02-10"}, "diet_notes", p); got != "b1" {
		t.Fatalf("got %s", got)
	}
	if got := RecordBlock(map[string]any{"date": "2026-07-01"}, "diet_notes", p); got != "b2" {
		t.Fatalf("got %s", got)
	}
	if got := RecordBlock(map[string]any{"block_id": "custom"}, "diet_notes", p); got != "custom" {
		t.Fatalf("got %s", got)
	}
	if got := RecordBlock(map[string]any{"block": "current"}, "diet_notes", p); got != "b2" {
		t.Fatalf("got %s", got)
	}
}

func TestProgramScopesListsAndRejectsNonRecords(t *testing.T) {
	scoped := Program(program(), "")
	notes := scoped["diet_notes"].([]any)
	if len(notes) != 2 {
		t.Fatalf("notes %v", notes)
	}
	past := Program(program(), "b1")["diet_notes"].([]any)
	if len(past) != 1 {
		t.Fatalf("past %v", past)
	}
}

func TestCurrentBlockFallsBackToActiveThenAlias(t *testing.T) {
	if got := CurrentBlockID(map[string]any{"meta": map[string]any{"blocks": []any{map[string]any{"id": "x", "status": "active"}}}}); got != "x" {
		t.Fatalf("got %s", got)
	}
	if got := CurrentBlockID(map[string]any{}); got != Active {
		t.Fatalf("got %s", got)
	}
}
