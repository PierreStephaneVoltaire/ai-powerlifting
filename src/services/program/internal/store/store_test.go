package store

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"powerlifting/program/internal/env"
	"powerlifting/program/internal/pyval"
)

type failingSupplementPut struct {
	DB
}

func (f failingSupplementPut) Put(ctx context.Context, table Table, item Item) error {
	if table == "sup" {
		return errors.New("supplement write failed")
	}
	return f.DB.Put(ctx, table, item)
}

func fixedEnv() env.Env {
	return env.Env{Now: func() time.Time { return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC) }, UUID: func() string { return "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" }}
}

func TestMemoryNormalizesNumbersLikeDynamo(t *testing.T) {
	db := NewMemory()
	if err := db.Seed("t", Item{"pk": "a", "sk": "b", "n": json.Number("100.0"), "f": 82.5, "i": int64(3), "nested": map[string]any{"x": json.Number("0.10")}}); err != nil {
		t.Fatal(err)
	}
	item, _ := db.Get(context.Background(), "t", Key{"a", "b"}, GetOptions{})
	if item["n"] != json.Number("100") || item["f"] != json.Number("82.5") || item["nested"].(map[string]any)["x"] != json.Number("0.1") {
		t.Fatalf("item %v", item)
	}
}

func TestMemoryRejectsUnsupportedTypes(t *testing.T) {
	if err := NewMemory().Put(context.Background(), "t", Item{"pk": "a", "sk": "b", "bad": struct{}{}}); err == nil {
		t.Fatal("unsupported type accepted")
	}
}

func TestSessionWindowQueryAndBlockFilter(t *testing.T) {
	db := NewMemory()
	tables := Tables{Sessions: "s", Health: "h"}
	sessions := Sessions{DB: db, Tables: tables, Env: fixedEnv()}
	for _, date := range []string{"2026-06-01", "2026-06-10", "2026-07-01"} {
		item := Item{"pk": "a", "sk": "session#p#" + date + "#001#id" + date, "date": date, "block": "b", "week_number": json.Number("1"), "same_day_ordinal": json.Number("1")}
		if err := db.Seed("s", item); err != nil {
			t.Fatal(err)
		}
	}
	all, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{})
	windowed, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{Start: "2026-06-05", End: "2026-06-30"})
	filtered, _ := sessions.List(context.Background(), "a", "p", nil, SessionWindow{BlockID: "other", ActiveBlock: "x"})
	if len(all) != 3 || len(windowed) != 1 || len(filtered) != 0 {
		t.Fatalf("all %d windowed %d filtered %d", len(all), len(windowed), len(filtered))
	}
}

func TestWriteFreshRejectsDuplicateIdentitiesAndUndatedSessions(t *testing.T) {
	db := NewMemory()
	sessions := Sessions{DB: db, Tables: Tables{Sessions: "s", Health: "h"}, Env: fixedEnv()}
	duplicate := []any{map[string]any{"date": "2026-01-01", "id": "x"}, map[string]any{"date": "2026-01-02", "id": "x"}}
	var conflict *IdentityConflictError
	if err := sessions.WriteFresh(context.Background(), "a", "program#bbb-abc", duplicate, nil); err == nil {
		t.Fatal("duplicate accepted")
	} else if c, ok := err.(*IdentityConflictError); !ok {
		t.Fatalf("err %v", err)
	} else {
		conflict = c
	}
	if conflict.ID != "x" || len(db.Dump("s")) != 0 {
		t.Fatalf("conflict %v writes %d", conflict, len(db.Dump("s")))
	}
	if err := sessions.WriteFresh(context.Background(), "a", "program#bbb-abc", []any{map[string]any{}}, nil); err != ErrSessionDate {
		t.Fatalf("err %v", err)
	}
}

func TestCommitMovesLegacySupplementsOutOfHealth(t *testing.T) {
	db := NewMemory()
	tables := Tables{Health: "h", Supplements: "sup"}
	legacy := Item{"pk": "a", "sk": "program#aaa", "meta": map[string]any{"current_block_id": "b"}, "supplements": []any{map[string]any{"name": "creatine"}}, "supplement_phases": []any{map[string]any{"block_id": "b"}}, "other": "keep"}
	if err := db.Seed("h", legacy); err != nil {
		t.Fatal(err)
	}
	programs := New(db, tables, fixedEnv())
	snapshot := &Snapshot{Program: pyval.CopyMap(legacy), SK: "program#aaa"}
	if _, err := programs.Commit(context.Background(), "a", snapshot, pyval.CopyMap(legacy)); err != nil {
		t.Fatal(err)
	}
	health, _ := db.Get(context.Background(), "h", Key{"a", "program#aaa"}, GetOptions{})
	supplements, _ := db.Get(context.Background(), "sup", Key{"a", "program#aaa"}, GetOptions{})
	if _, ok := health["supplements"]; ok {
		t.Fatalf("health retained supplements: %v", health)
	}
	if supplements["supplements"] == nil || supplements["supplement_phases"] == nil || health["other"] != "keep" {
		t.Fatalf("health %v supplements %v", health, supplements)
	}
}

func TestCommitDoesNotRewriteUnchangedSupplements(t *testing.T) {
	db := NewMemory()
	tables := Tables{Health: "h", Supplements: "sup"}
	stored := Item{"pk": "a", "sk": "program#aaa", "supplements": []any{map[string]any{"name": "new"}}, "supplement_phases": []any{}}
	if err := db.Seed("sup", stored); err != nil {
		t.Fatal(err)
	}
	programs := New(db, tables, fixedEnv())
	program := Item{"meta": map[string]any{}, "supplements": []any{map[string]any{"name": "stale"}}, "supplement_phases": []any{}, "notes": "updated"}
	snapshot := &Snapshot{Program: pyval.CopyMap(program), SK: "program#aaa"}
	if _, err := programs.Commit(context.Background(), "a", snapshot, program); err != nil {
		t.Fatal(err)
	}
	supplements, _ := db.Get(context.Background(), "sup", Key{"a", "program#aaa"}, GetOptions{})
	if supplements["supplements"].([]any)[0].(map[string]any)["name"] != "new" {
		t.Fatalf("supplements overwritten: %v", supplements)
	}
}

func TestSupplementRowDoesNotResurrectMissingLegacyFields(t *testing.T) {
	db := NewMemory()
	programs := New(db, Tables{Supplements: "sup"}, fixedEnv())
	program := Item{"supplements": []any{"legacy supplements"}, "supplement_phases": []any{"legacy phases"}}
	if err := db.Seed("sup", Item{"pk": "a", "sk": "program#aaa", "supplements": []any{"new supplements"}}); err != nil {
		t.Fatal(err)
	}
	if err := programs.loadSupplements(context.Background(), "a", "program#aaa", program); err != nil {
		t.Fatal(err)
	}
	if program["supplement_phases"] != nil || program["supplements"].([]any)[0] != "new supplements" {
		t.Fatalf("hydrated supplements: %v", program)
	}
}

func TestCommitKeepsLegacyDataWhenSupplementWriteFails(t *testing.T) {
	db := NewMemory()
	legacy := Item{"pk": "a", "sk": "program#aaa", "meta": map[string]any{}, "supplements": []any{"legacy"}, "note": "old"}
	if err := db.Seed("h", legacy); err != nil {
		t.Fatal(err)
	}
	program := pyval.CopyMap(legacy)
	program["note"] = "new"
	programs := New(failingSupplementPut{DB: db}, Tables{Health: "h", Supplements: "sup"}, fixedEnv())
	if _, err := programs.Commit(context.Background(), "a", &Snapshot{Program: pyval.CopyMap(legacy), SK: "program#aaa"}, program); err == nil {
		t.Fatal("commit succeeded")
	}
	stored, _ := db.Get(context.Background(), "h", Key{"a", "program#aaa"}, GetOptions{})
	if stored["supplements"] == nil || stored["note"] != "old" {
		t.Fatalf("legacy program changed after failed supplement write: %v", stored)
	}
}

func TestCommitPreservesUnchangedSupplementField(t *testing.T) {
	db := NewMemory()
	current := Item{"pk": "a", "sk": "program#aaa", "supplements": []any{"current"}, "supplement_phases": []any{"old phase"}}
	if err := db.Seed("sup", current); err != nil {
		t.Fatal(err)
	}
	program := Item{"meta": map[string]any{}, "supplements": []any{"old supplement"}, "supplement_phases": []any{"old phase"}}
	snapshot := &Snapshot{Program: pyval.CopyMap(program), SK: "program#aaa"}
	program["supplement_phases"] = []any{"new phase"}
	programs := New(db, Tables{Health: "h", Supplements: "sup"}, fixedEnv())
	if _, err := programs.Commit(context.Background(), "a", snapshot, program); err != nil {
		t.Fatal(err)
	}
	stored, _ := db.Get(context.Background(), "sup", Key{"a", "program#aaa"}, GetOptions{})
	if stored["supplements"].([]any)[0] != "current" || stored["supplement_phases"].([]any)[0] != "new phase" {
		t.Fatalf("supplement merge: %v", stored)
	}
}

func TestSaveProgramChecksPointerAndImportClaim(t *testing.T) {
	ctx := context.Background()
	db := NewMemory()
	tables := Tables{Health: "h"}
	for _, item := range []Item{
		{"pk": "a", "sk": PointerSK, "ref_sk": "program#one"},
		{"pk": "a", "sk": "import#pending#i", "status": "applying", "apply_claim_id": "claim"},
	} {
		if err := db.Seed(tables.Health, item); err != nil {
			t.Fatal(err)
		}
	}
	program := Item{"pk": "a", "sk": "program#one", "meta": map[string]any{}}
	if err := db.SaveProgram(ctx, tables, "a", program, "program#stale", "b", "now", "i", "claim"); err == nil {
		t.Fatal("accepted a stale program pointer")
	}
	if err := db.SaveProgram(ctx, tables, "a", program, "program#one", "b", "now", "i", "stale"); err == nil {
		t.Fatal("accepted a stale import claim")
	}
	if err := db.SaveProgram(ctx, tables, "a", program, "program#one", "b", "now", "i", "claim"); err != nil {
		t.Fatal(err)
	}
	got, _ := db.Get(ctx, tables.Health, Key{"a", PointerSK}, GetOptions{})
	saved, _ := db.Get(ctx, tables.Health, Key{"a", "program#one"}, GetOptions{})
	if got["ref_sk"] != "program#one" || got["current_block_id"] != "b" || got["updated_at"] != "now" || saved == nil {
		t.Fatalf("pointer %v program %v", got, saved)
	}
}
