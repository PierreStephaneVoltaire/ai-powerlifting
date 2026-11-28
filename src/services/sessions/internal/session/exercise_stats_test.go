package session_test

import (
	"context"
	"encoding/json"
	"testing"

	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/store"
	"powerlifting/sessions/internal/value"
)

func setupStatsService(t *testing.T) (*session.Service, *store.Memory) {
	t.Helper()
	mem := store.NewMemory()
	mem.SeedHealth(value.Item{"pk": "athlete_1", "sk": "program#current", "ref_sk": "program#v001"})
	mem.SeedHealth(value.Item{"pk": "athlete_1", "sk": "program#v001", "phases": []any{}})
	svc := &session.Service{Sessions: mem, Programs: mem, SourceTable: "if-health"}
	return svc, mem
}

func TestExerciseHistoryAndPRs(t *testing.T) {
	svc, mem := setupStatsService(t)
	ctx := context.Background()

	mem.SeedSession(value.Item{
		"pk": "athlete_1", "sk": "session#program#v001#2026-10-01#001#s0",
		"session_id": "s0", "date": "2026-10-01", "program_sk": "program#v001",
		"block": "archived-block", "completed": true,
		"exercises": []any{
			map[string]any{"name": "Competition Squat", "sets": json.Number("1"), "reps": json.Number("1"), "kg": json.Number("250")},
		},
	})
	mem.SeedSession(value.Item{
		"pk": "athlete_1", "sk": "session#program#v001#2026-10-10#001#s1",
		"session_id": "s1", "date": "2026-10-10", "program_sk": "program#v001",
		"completed": true,
		"exercises": []any{
			map[string]any{"name": "Competition Squat", "sets": json.Number("3"), "reps": json.Number("5"), "kg": json.Number("140.0")},
		},
	})
	mem.SeedSession(value.Item{
		"pk": "athlete_1", "sk": "session#program#v001#2026-10-17#001#s2",
		"session_id": "s2", "date": "2026-10-17", "program_sk": "program#v001",
		"block": "current", "completed": false,
		"exercises": []any{
			map[string]any{
				"name": "Competition Squats (Beltless)",
				"sets": json.Number("4"),
				"sets_data": []any{
					map[string]any{"reps": json.Number("3"), "kg": json.Number("160")},
					map[string]any{"reps": json.Number("3"), "kg": json.Number("160.0")},
					map[string]any{"reps": json.Number("3"), "kg": json.Number("165")},
					map[string]any{"reps": json.Number("3"), "kg": json.Number("165")},
				},
				"set_statuses": []any{"completed", "completed", "failed", "skipped"},
			},
			map[string]any{
				"name": "Plank", "rep_unit": "seconds", "sets": json.Number("1"), "reps": json.Number("10"), "kg": json.Number("200"),
				"set_statuses": []any{"completed"},
			},
		},
	})
	mem.SeedSession(value.Item{
		"pk": "athlete_1", "sk": "session#program#v001#2026-10-20#001#s3",
		"session_id": "s3", "date": "2026-10-20", "program_sk": "program#v001",
		"completed": true,
		"exercises": []any{
			map[string]any{"name": "Competition Squat", "sets": json.Number("1"), "reps": json.Number("15"), "kg": json.Number("100")},
			map[string]any{"name": "Competition Squat", "sets": json.Number("1"), "reps": json.Number("2"), "kg": json.Number("170")},
		},
	})

	historyRes, err := svc.ExerciseHistory(ctx, "athlete_1", "Competition Squat", "s3")
	if err != nil {
		t.Fatal(err)
	}
	entries := historyRes["entries"].([]any)
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries, got %d: %v", len(entries), entries)
	}
	first := entries[0].(value.Item)
	second := entries[1].(value.Item)
	third := entries[2].(value.Item)
	if first["date"] != "2026-10-17" || first["sets"] != value.Int(2) || first["reps"] != json.Number("3") || first["kg"] != json.Number("160") || first["status"] != "completed" {
		t.Fatalf("unexpected first entry: %v", first)
	}
	if second["date"] != "2026-10-17" || second["sets"] != value.Int(1) || second["kg"] != json.Number("165") || second["status"] != "failed" {
		t.Fatalf("unexpected second entry: %v", second)
	}
	if third["date"] != "2026-10-10" || third["sets"] != value.Int(3) || third["reps"] != json.Number("5") || third["kg"] != json.Number("140") || third["status"] != "completed" {
		t.Fatalf("unexpected third entry: %v", third)
	}

	prsRes, err := svc.ExercisePRs(ctx, "athlete_1", "Competition Squat")
	if err != nil {
		t.Fatal(err)
	}
	records := prsRes["records"].([]any)
	if len(records) != 3 {
		t.Fatalf("expected 3 PR records, got %d: %v", len(records), records)
	}
	r2 := records[0].(value.Item)
	r3 := records[1].(value.Item)
	r5 := records[2].(value.Item)
	if r2["reps"] != value.Int(2) || r2["kg"] != json.Number("170") || r2["date"] != "2026-10-20" {
		t.Fatalf("unexpected 2RM: %v", r2)
	}
	if r3["reps"] != value.Int(3) || r3["kg"] != json.Number("160") || r3["date"] != "2026-10-17" {
		t.Fatalf("unexpected 3RM: %v", r3)
	}
	if r5["reps"] != value.Int(5) || r5["kg"] != json.Number("140") || r5["date"] != "2026-10-10" {
		t.Fatalf("unexpected 5RM: %v", r5)
	}

	plankPRs, err := svc.ExercisePRs(ctx, "athlete_1", "Plank")
	if err != nil {
		t.Fatal(err)
	}
	if len(plankPRs["records"].([]any)) != 0 {
		t.Fatalf("expected no PRs for timed exercise, got %v", plankPRs)
	}
}
