package publication

import "testing"

func TestAnalyticsOnlyCannotSeeUnpublishedProgramOrPrivateSessions(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"program_name": "secret", "training_notes": []any{"private"}}, "sessions": []any{map[string]any{"block": "current", "videos": []any{"secret"}}}, "competitions": []any{map[string]any{"master_id": "private"}}}
	access := Access{"permissions": []any{"analytics:read"}, "granted_permissions": []any{"analytics:read"}}
	view := ProgramView(program, access)
	if len(view["sessions"].([]any)) != 0 || len(view["competitions"].([]any)) != 0 || len(view["meta"].(map[string]any)) != 0 {
		t.Fatalf("unexpected disclosure %#v", view)
	}
}

func TestProgramViewFiltersCompetitionAndPrivateNotes(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"block_notes": []any{map[string]any{"private": true, "notes": "secret"}, map[string]any{"notes": "shared"}}}, "competitions": []any{map[string]any{"master_id": "one"}, map[string]any{"master_id": "two"}}}
	access := Access{"permissions": []any{"program:read", "competition:read"}, "competition_scope": map[string]any{"read": []any{"COMP#one"}}}
	view := ProgramView(program, access)
	if len(view["competitions"].([]any)) != 1 || len(view["meta"].(map[string]any)["block_notes"].([]any)) != 1 {
		t.Fatalf("unexpected view %#v", view)
	}
}
