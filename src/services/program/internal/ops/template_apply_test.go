package ops

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"

	"powerlifting/program/internal/store"
)

func TestTemplateApplyPreservesLoggedWork(t *testing.T) {
	for _, target := range []string{"append", "replace_incomplete"} {
		t.Run(target, func(t *testing.T) {
			deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"blocks": []any{map[string]any{"id": "b1", "status": "active"}}}})
			ctx := context.Background()
			existing := []any{map[string]any{"id": "old", "date": "2026-11-23", "status": "completed", "exercises": []any{}}, map[string]any{"id": "planned", "date": "2026-11-24", "status": "planned", "exercises": []any{}}}
			if err := deps.Programs.Sessions.WriteFresh(ctx, "a1", "program#v002", existing, nil); err != nil {
				t.Fatal(err)
			}
			args := map[string]any{"target": target, "block_id": "b1", "sk": "template#1", "start_date": "2026-11-23", "week_start_day": "Monday", "sessions": []any{map[string]any{"date": "2026-11-23"}}}
			result, err := templateApplySessions(deps, notesRequest(args))
			if err != nil {
				t.Fatal(err)
			}
			written := result.(map[string]any)
			loaded, err := deps.Programs.Load(ctx, "a1", written["program_sk"].(string), true)
			if err != nil {
				t.Fatal(err)
			}
			sessions := loaded.Program["sessions"].([]any)
			want := 2
			if target == "append" {
				want = 3
			}
			if len(sessions) != want {
				t.Fatalf("%s sessions: %#v", target, sessions)
			}
		})
	}
}

func TestTemplateApplyRejectsInactiveBlock(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"blocks": []any{map[string]any{"id": "b1", "status": "completed"}}}})
	_, err := templateApplySessions(deps, notesRequest(map[string]any{"target": "append", "block_id": "b1", "start_date": "2026-11-23"}))
	if err == nil {
		t.Fatal("expected inactive block to be rejected")
	}
}

func TestTemplateApplyRetryDoesNotAppendTwice(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"blocks": []any{map[string]any{"id": "b1", "status": "active"}}}})
	args := map[string]any{"target": "append", "block_id": "b1", "sk": "template#1", "start_date": "2026-11-23", "week_start_day": "Monday", "operation_id": "job-and-request", "sessions": []any{map[string]any{"date": "2026-11-23"}}}
	first, err := templateApplySessions(deps, notesRequest(args))
	if err != nil {
		t.Fatal(err)
	}
	second, err := templateApplySessions(deps, notesRequest(args))
	if err != nil {
		t.Fatal(err)
	}
	if first.(map[string]any)["program_sk"] != second.(map[string]any)["program_sk"] {
		t.Fatalf("retry created another program: %v %v", first, second)
	}
	loaded, err := deps.Programs.Load(context.Background(), "a1", "", true)
	if err != nil || len(loaded.Program["sessions"].([]any)) != 1 {
		t.Fatalf("retry sessions: %#v, %v", loaded, err)
	}
}

func TestTemplateBlockTransitionRetryDoesNotCreateAnotherVersion(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"blocks": []any{map[string]any{"id": "b1", "status": "active"}}, "current_block_id": "b1"}})
	args := map[string]any{"action": "complete", "block_id": "b1", "operation_id": "retry"}
	first, err := blockTransition(deps, notesRequest(args))
	if err != nil {
		t.Fatal(err)
	}
	second, err := blockTransition(deps, notesRequest(args))
	if err != nil {
		t.Fatal(err)
	}
	firstProgram := first.(map[string]any)["program"].(map[string]any)
	secondProgram := second.(map[string]any)["program"].(map[string]any)
	if firstProgram["sk"] != secondProgram["sk"] {
		t.Fatalf("retry created another program: %v %v", firstProgram["sk"], secondProgram["sk"])
	}
}

func TestConcurrentTemplateApplyCanRetryWithoutDuplicates(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v002"), store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"blocks": []any{map[string]any{"id": "b1", "status": "active"}}}})
	var sequence atomic.Int64
	newID := func() string { return fmt.Sprintf("00000000-0000-4000-8000-%012d", sequence.Add(1)) }
	deps.Env.UUID, deps.Programs.Env.UUID, deps.Programs.Sessions.Env.UUID = newID, newID, newID
	args := func() map[string]any {
		return map[string]any{"target": "append", "block_id": "b1", "sk": "template#1", "start_date": "2026-11-23", "week_start_day": "Monday", "operation_id": "same-attempt", "sessions": []any{map[string]any{"date": "2026-11-23"}}}
	}
	var wg sync.WaitGroup
	wg.Add(2)
	for range 2 {
		go func() {
			defer wg.Done()
			_, _ = templateApplySessions(deps, notesRequest(args()))
		}()
	}
	wg.Wait()
	if _, err := templateApplySessions(deps, notesRequest(args())); err != nil {
		t.Fatal(err)
	}
	loaded, err := deps.Programs.Load(context.Background(), "a1", "", true)
	if err != nil || len(loaded.Program["sessions"].([]any)) != 1 {
		t.Fatalf("duplicate sessions after concurrent retry: %#v, %v", loaded, err)
	}
}
