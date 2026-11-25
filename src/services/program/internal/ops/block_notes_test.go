package ops

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"powerlifting/program/internal/env"
	"powerlifting/program/internal/store"
)

func notesDeps(t *testing.T, items ...store.Item) (*Deps, *store.Memory) {
	t.Helper()
	db := store.NewMemory()
	tables := store.Tables{Health: "h", Sessions: "s", Supplements: "sup", Competitions: "c", Templates: "t"}
	if err := db.Seed(tables.Health, items...); err != nil {
		t.Fatal(err)
	}
	runtime := env.Env{
		Now:  func() time.Time { return time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC) },
		UUID: func() string { return "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" },
	}
	return &Deps{Programs: store.New(db, tables, runtime), Env: runtime}, db
}

func notesRequest(args map[string]any) *Request {
	return &Request{Ctx: context.Background(), Athlete: "a1", Args: args}
}

func pointerTo(sk string) store.Item {
	return store.Item{"pk": "a1", "sk": "program#current", "version": int64(2), "ref_sk": sk}
}

func storedNotes(t *testing.T, db *store.Memory, sk string) []any {
	t.Helper()
	item, err := db.Get(context.Background(), "h", store.Key{PK: "a1", SK: sk}, store.GetOptions{})
	if err != nil || item == nil {
		t.Fatalf("read %s: %v %v", sk, item, err)
	}
	meta, _ := item["meta"].(map[string]any)
	notes, _ := meta["block_notes"].([]any)
	return notes
}

func TestBlockNotesUpdateIgnoresOldVersionSelector(t *testing.T) {
	deps, db := notesDeps(t,
		pointerTo("program#v002"),
		store.Item{"pk": "a1", "sk": "program#v001", "meta": map[string]any{"current_block_id": "b1", "block_notes": []any{}}},
		store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"current_block_id": "b2", "block_notes": []any{}}},
	)
	notes := []any{map[string]any{"notes": "current note", "block_id": "b2"}}
	if _, err := blockNotesUpdate(deps, notesRequest(map[string]any{"version": "v001", "block_notes": notes})); err != nil {
		t.Fatal(err)
	}
	if got := storedNotes(t, db, "program#v001"); len(got) != 0 {
		t.Fatalf("old program was modified %v", got)
	}
	if got := storedNotes(t, db, "program#v002"); len(got) != 1 {
		t.Fatalf("current program notes %v", got)
	}
}

func TestBlockNotesUpdateDefaultsAndCurrentVersionWriteCurrentProgram(t *testing.T) {
	for _, args := range []map[string]any{{}, {"version": "current"}} {
		deps, db := notesDeps(t,
			pointerTo("program#v002"),
			store.Item{"pk": "a1", "sk": "program#v001", "meta": map[string]any{"current_block_id": "b1"}},
			store.Item{"pk": "a1", "sk": "program#v002", "meta": map[string]any{"current_block_id": "b2"}},
		)
		args["block_notes"] = []any{map[string]any{"notes": "n", "block_id": "b2"}}
		if _, err := blockNotesUpdate(deps, notesRequest(args)); err != nil {
			t.Fatal(err)
		}
		if len(storedNotes(t, db, "program#v002")) != 1 || len(storedNotes(t, db, "program#v001")) != 0 {
			t.Fatalf("args %v did not write the current program", args)
		}
	}
}

func TestBlockNotesGetReturnsEmptyListWhenVersionHasNoNotes(t *testing.T) {
	cases := map[string]store.Item{
		"no_meta":          {"pk": "a1", "sk": "program#v001"},
		"empty_meta":       {"pk": "a1", "sk": "program#v001", "meta": map[string]any{}},
		"meta_without":     {"pk": "a1", "sk": "program#v001", "meta": map[string]any{"program_name": "x"}},
		"null_block_notes": {"pk": "a1", "sk": "program#v001", "meta": map[string]any{"block_notes": nil}},
	}
	for name, item := range cases {
		for _, version := range []string{"v001", "current", ""} {
			deps, _ := notesDeps(t, pointerTo("program#v001"), item)
			args := map[string]any{}
			if version != "" {
				args["version"] = version
			}
			result, err := blockNotesGet(deps, notesRequest(args))
			if err != nil {
				t.Fatalf("%s/%q: %v", name, version, err)
			}
			encoded, _ := json.Marshal(result.(map[string]any)["block_notes"])
			if string(encoded) != "[]" {
				t.Fatalf("%s/%q: block_notes %s", name, version, encoded)
			}
		}
	}
}

func privateNotesProgram() store.Item {
	return store.Item{"pk": "a1", "sk": "program#v001", "meta": map[string]any{"current_block_id": "b1", "block_notes": []any{
		map[string]any{"date": "2026-11-01", "notes": "shared", "block_id": "b1"},
		map[string]any{"date": "2026-11-02", "notes": "mine", "block_id": "b1", "private": true},
	}}}
}

func noteTexts(notes any) []string {
	texts := []string{}
	list, _ := notes.([]any)
	for _, raw := range list {
		texts = append(texts, raw.(map[string]any)["notes"].(string))
	}
	return texts
}

func TestOtherPeopleDoNotSeePrivateBlockNotes(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v001"), privateNotesProgram())
	result, err := blockNotesGet(deps, notesRequest(map[string]any{}))
	if err != nil {
		t.Fatal(err)
	}
	coach := Access{"is_self": false, "permissions": []any{"program:read"}}
	if got := noteTexts(OperationResult("block_notes_get", result, coach).(map[string]any)["block_notes"]); len(got) != 1 || got[0] != "shared" {
		t.Fatalf("coach saw %v", got)
	}
	program := map[string]any{"meta": map[string]any{"block_notes": privateNotesProgram()["meta"].(map[string]any)["block_notes"]}}
	if got := noteTexts(ProgramView(program, coach)["meta"].(map[string]any)["block_notes"]); len(got) != 1 || got[0] != "shared" {
		t.Fatalf("coach program view saw %v", got)
	}
}

func TestAthleteSeesOwnPrivateBlockNotes(t *testing.T) {
	deps, _ := notesDeps(t, pointerTo("program#v001"), privateNotesProgram())
	result, err := blockNotesGet(deps, notesRequest(map[string]any{}))
	if err != nil {
		t.Fatal(err)
	}
	owner := Access{"is_self": true, "permissions": []any{"program:read"}}
	if got := noteTexts(OperationResult("block_notes_get", result, owner).(map[string]any)["block_notes"]); len(got) != 2 {
		t.Fatalf("athlete saw %v", got)
	}
	program := map[string]any{"meta": map[string]any{"block_notes": privateNotesProgram()["meta"].(map[string]any)["block_notes"]}}
	if got := noteTexts(ProgramView(program, owner)["meta"].(map[string]any)["block_notes"]); len(got) != 2 {
		t.Fatalf("athlete program view saw %v", got)
	}
}

func TestDelegateUpdateKeepsPrivateNotesAndCannotMarkPrivate(t *testing.T) {
	deps, db := notesDeps(t, pointerTo("program#v001"), privateNotesProgram())
	request := notesRequest(map[string]any{"block_notes": []any{
		map[string]any{"date": "2026-11-01", "notes": "shared edited", "block_id": "b1"},
		map[string]any{"date": "2026-11-03", "notes": "coach", "block_id": "b1", "private": true},
	}})
	request.Access = map[string]any{"is_self": false}
	if _, err := blockNotesUpdate(deps, request); err != nil {
		t.Fatal(err)
	}
	stored := storedNotes(t, db, "program#v001")
	byText := map[string]map[string]any{}
	for _, raw := range stored {
		note := raw.(map[string]any)
		byText[note["notes"].(string)] = note
	}
	if len(stored) != 3 || byText["mine"]["private"] != true || byText["coach"] == nil || byText["coach"]["private"] != nil || byText["shared edited"] == nil {
		t.Fatalf("stored %v", stored)
	}
}

func TestAthleteUpdateCanRemoveAndMarkPrivateNotes(t *testing.T) {
	deps, db := notesDeps(t, pointerTo("program#v001"), privateNotesProgram())
	request := notesRequest(map[string]any{"block_notes": []any{
		map[string]any{"date": "2026-11-01", "notes": "shared", "block_id": "b1", "private": true},
	}})
	request.Access = map[string]any{"is_self": true}
	if _, err := blockNotesUpdate(deps, request); err != nil {
		t.Fatal(err)
	}
	stored := storedNotes(t, db, "program#v001")
	if len(stored) != 1 || stored[0].(map[string]any)["private"] != true {
		t.Fatalf("stored %v", stored)
	}
}
