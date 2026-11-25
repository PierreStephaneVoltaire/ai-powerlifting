package ops

import (
	"context"
	"testing"

	"powerlifting/program/internal/store"
)

func TestApplySessionImportAndRetry(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#bbb"),
		store.Item{"pk": "a1", "sk": "program#bbb", "meta": map[string]any{}},
		store.Item{"pk": "a1", "sk": "import#pending#i1", "status": "applying", "apply_claim_id": "c1"})
	if err := deps.Programs.Sessions.WriteFresh(context.Background(), "a1", "program#bbb", []any{map[string]any{"id": "old", "date": "2026-11-20", "exercises": []any{map[string]any{"name": "squat"}}}}, nil); err != nil {
		t.Fatal(err)
	}
	args := map[string]any{"import_id": "i1", "claim_id": "c1", "start_date": "2026-11-20", "sessions": []any{map[string]any{"date": "2026-10-01", "exercises": []any{map[string]any{"name": "bench"}}}, map[string]any{"date": "2026-10-02", "exercises": []any{}}}}
	first, err := programApplySessionImport(deps, notesRequest(args))
	if err != nil {
		t.Fatal(err)
	}
	result := first.(map[string]any)
	if result["applied_count"] != 2 {
		t.Fatalf("unexpected result: %#v", result)
	}
	second, err := programApplySessionImport(deps, notesRequest(args))
	if err != nil || second.(map[string]any)["status"] != "applied" {
		t.Fatalf("retry: %#v, %v", second, err)
	}
	loaded, err := deps.Programs.Load(context.Background(), "a1", true)
	if err != nil {
		t.Fatal(err)
	}
	sessions := loaded.Program["sessions"].([]any)
	if len(sessions) != 2 || len(sessions[0].(map[string]any)["exercises"].([]any)) != 2 {
		t.Fatalf("unexpected sessions: %#v", sessions)
	}
}

func TestApplySessionImportRejectsUnclaimedImport(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#bbb"), store.Item{"pk": "a1", "sk": "program#bbb", "meta": map[string]any{}}, store.Item{"pk": "a1", "sk": "import#pending#i1", "status": "applying", "apply_claim_id": "other"})
	if _, err := programApplySessionImport(deps, notesRequest(map[string]any{"import_id": "i1", "claim_id": "c1"})); err == nil {
		t.Fatal("expected invalid claim to fail")
	}
}

func TestImportConflictResolutions(t *testing.T) {
	existing := []map[string]any{
		{"date": "2026-01-01", "exercises": []any{"old"}},
		{"date": "2026-01-02", "exercises": []any{"old"}},
		{"date": "2026-01-03", "exercises": []any{"old"}},
	}
	staged := []map[string]any{
		{"date": "2026-01-01", "exercises": []any{"new"}},
		{"date": "2026-01-02", "exercises": []any{"new"}},
		{"date": "2026-01-03", "exercises": []any{"new"}},
	}
	resolutions := []map[string]any{{"session_date": "2026-01-01", "action": "skip"}, {"session_date": "2026-01-02", "action": "overwrite"}, {"session_date": "2026-01-03", "action": "merge"}}
	merged, applied, skipped, err := importSessions(existing, staged, "", "selective", resolutions)
	if err != nil || applied != 2 || skipped != 1 {
		t.Fatalf("counts %d/%d: %v", applied, skipped, err)
	}
	for i, want := range []int{1, 1, 2} {
		exercises := merged[i].(map[string]any)["exercises"].([]any)
		if len(exercises) != want {
			t.Fatalf("session %d: %v", i, exercises)
		}
	}
	if merged[1].(map[string]any)["exercises"].([]any)[0] != "new" {
		t.Fatal("overwrite did not replace exercises")
	}
	if _, _, _, err := importSessions(nil, []map[string]any{{"date": "invalid"}}, "2026-01-01", "append", nil); err == nil {
		t.Fatal("invalid date accepted")
	}
}
