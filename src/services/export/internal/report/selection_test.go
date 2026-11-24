package report

import (
	"encoding/json"
	"testing"
)

func TestExportSelectionNaming(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"program_name": "Base", "current_block_id": "new", "blocks": []any{map[string]any{"id": "new", "name": "Offseason Session"}, map[string]any{"id": "old", "name": "Sunny Daze + APEX Prep"}}}}
	for _, tc := range []struct {
		block, extension, want string
		window                 map[string]any
	}{
		{"current", "md", "offseason-session_W1-W3.md", map[string]any{"week_start": 1, "week_end": 3}},
		{"old", "xlsx", "sunny-daze-apex-prep.xlsx", nil},
		{"unknown", "md", "base_2026-11-01_2026-11-30.md", map[string]any{"window_start": "2026-11-01", "window_end": "2026-11-30"}},
	} {
		if got := Filename(program, tc.block, tc.window, tc.extension); got != tc.want {
			t.Errorf("got %q want %q", got, tc.want)
		}
	}
	for _, input := range []string{"md", "MARKDOWN", " markdown "} {
		if got, err := NormalizeFormat(input); err != nil || got != "markdown" {
			t.Fatalf("%q: %q %v", input, got, err)
		}
	}
	if _, err := NormalizeFormat("pdf"); err == nil {
		t.Fatal("accepted invalid format")
	}
}

func TestEntryWindowUsesBlockBoundariesBeforeSessionDates(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"current_block_id": "one", "blocks": []any{map[string]any{"id": "two", "start_date": "2026-12-01"}, map[string]any{"id": "one", "start_date": "2026-11-01"}}}}
	sessions := []any{map[string]any{"date": "2026-11-10"}, map[string]any{"date": "2026-11-20"}}
	start, end := EntryWindow(program, "current", nil, sessions)
	if start != "2026-11-01" || end != "2026-11-30" {
		t.Fatalf("got %s through %s", start, end)
	}
	start, end = EntryWindow(program, "current", map[string]any{"window_start": "2026-11-15"}, sessions)
	if start != "2026-11-15" || end != "2026-11-20" {
		t.Fatalf("got %s through %s", start, end)
	}
}

func TestSessionsInWindowHonorsWeekRangeOrDateRange(t *testing.T) {
	sessions := []any{map[string]any{"date": "2026-10-01T12:00:00Z", "week_number": 1.0}, map[string]any{"date": "2026-10-08", "week_number": 2.0}, map[string]any{"date": "2026-10-15", "week_number": 3.0}}
	for _, tc := range []struct {
		window map[string]any
		want   string
	}{
		{map[string]any{"week_start": json.Number("2"), "week_end": json.Number("2"), "window_start": "2026-10-15"}, "2026-10-08"},
		{map[string]any{"window_start": "2026-10-08", "window_end": "2026-10-14"}, "2026-10-08"},
	} {
		got := SessionsInWindow(sessions, tc.window)
		if len(got) != 1 || got[0].(map[string]any)["date"] != tc.want {
			t.Fatalf("got %#v, want %s", got, tc.want)
		}
	}
}
