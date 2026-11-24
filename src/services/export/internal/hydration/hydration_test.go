package hydration

import (
	"context"
	"testing"
)

type fakeReader struct {
	items map[string]map[string]any
	lists map[string][]map[string]any
}

func (f fakeReader) Get(_ context.Context, table, _, sk string) (map[string]any, error) {
	return f.items[table+"/"+sk], nil
}
func (f fakeReader) Query(_ context.Context, table, _, prefix string) ([]map[string]any, error) {
	return f.lists[table+"/"+prefix], nil
}
func (f fakeReader) Competitions(context.Context, string, string, string) ([]map[string]any, error) {
	return f.lists["competitions"], nil
}

func TestLoadDefaultsToCurrentBlockAndPreservesPrivateNotesForOwner(t *testing.T) {
	fake := fakeReader{items: map[string]map[string]any{
		"health/program#current": {"ref_sk": "program#v001", "version": 1},
		"health/program#v001":    {"meta": map[string]any{"current_block_id": "new", "block_notes": []any{map[string]any{"block_id": "new", "private": true}}}, "phases": []any{}},
	}, lists: map[string][]map[string]any{
		"sessions/session#program#v001#": {{"sk": "one", "block_id": "old", "date": "2026-01-01"}, {"sk": "two", "block_id": "new", "date": "2026-02-01"}},
	}}
	loader := Loader{Reader: fake, Tables: Tables{Health: "health", Sessions: "sessions", Supplements: "supplements"}}
	result, err := loader.Load(context.Background(), "athlete", "", "", "", map[string]any{"is_self": true, "permissions": []any{"program:read", "sessions:read"}})
	if err != nil {
		t.Fatal(err)
	}
	sessions := result.Program["sessions"].([]any)
	if len(sessions) != 1 || sessions[0].(map[string]any)["date"] != "2026-02-01" {
		t.Fatalf("sessions: %#v", sessions)
	}
	notes := result.Program["meta"].(map[string]any)["block_notes"].([]any)
	if len(notes) != 1 {
		t.Fatalf("notes: %#v", notes)
	}
}

func TestLoadFallbackSelectsHighestPublishedNumericVersion(t *testing.T) {
	fake := fakeReader{items: map[string]map[string]any{
		"health/program#v012-older": {"meta": map[string]any{}, "phases": []any{}},
	}, lists: map[string][]map[string]any{
		"health/program#": {{"sk": "program#v002"}, {"sk": "program#v012-older"}, {"sk": "program#v999", "published": false}, {"sk": "program#current"}},
	}}
	loader := Loader{Reader: fake, Tables: Tables{Health: "health", Sessions: "sessions", Supplements: "supplements"}}
	result, err := loader.Load(context.Background(), "athlete", "all", "", "", nil)
	if err != nil || result.ProgramSK != "program#v012-older" || result.Version != 12 {
		t.Fatalf("result=%#v err=%v", result, err)
	}
}
