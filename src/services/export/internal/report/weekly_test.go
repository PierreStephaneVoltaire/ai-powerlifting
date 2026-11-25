package report

import (
	"reflect"
	"testing"
)

func TestWeeklyTablesRenderPercentagesAndKeepZeroAndFalse(t *testing.T) {
	weekly := map[string]any{
		"readiness_score":        map[string]any{"score": 0.0, "zone": "yellow", "components": map[string]any{"fatigue_norm": 0.321}},
		"projection_calibration": map[string]any{"calibrated": false},
		"projections":            []any{map[string]any{"comp_name": "Meet", "lifts": map[string]any{"squat": map[string]any{"projected": 180.0}}, "confidence": 0.726}},
	}
	tables := WeeklyTables(weekly)
	if len(tables) != 3 {
		t.Fatalf("tables %#v", tables)
	}
	want := [][]any{{"Overall score", 0.0}, {"Zone", "yellow"}, {"Fatigue (%)", 32.1}}
	if !reflect.DeepEqual(tables[0].Rows, want) {
		t.Fatalf("readiness %#v", tables[0].Rows)
	}
	if !reflect.DeepEqual(tables[2].Rows, [][]any{{"Calibrated", false}}) {
		t.Fatal(tables[2].Rows)
	}
	if got := tables[1].Rows[0]; got[2] != 180.0 || got[6] != 72.6 {
		t.Fatal(got)
	}
}
