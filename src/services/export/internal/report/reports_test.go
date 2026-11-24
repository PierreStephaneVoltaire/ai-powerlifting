package report

import (
	"reflect"
	"testing"
)

func TestCachedReportsRespectAnalysisPermissionAndWindow(t *testing.T) {
	sessions := []any{map[string]any{"completed": true}, map[string]any{"completed": true}, map[string]any{"completed": true}, map[string]any{"completed": true}}
	window := map[string]any{"window_key": "block", "week_start": 1, "week_end": 4}
	if got := CachedReports("current", window, sessions, map[string]any{"permissions": []any{"analytics:read"}}); !reflect.DeepEqual(got, []string{"analytics.correlation", "analytics.block_evaluation"}) {
		t.Fatal(got)
	}
	if got := CachedReports("current", window, sessions, map[string]any{"permissions": []any{"program:read"}}); len(got) != 0 {
		t.Fatal(got)
	}
	if got := CachedReports("old", window, sessions, nil); len(got) != 0 {
		t.Fatal(got)
	}
	window["window_key"] = "previous_2"
	window["week_end"] = 2
	if got := CachedReports("current", window, sessions, nil); len(got) != 0 {
		t.Fatal(got)
	}
}
