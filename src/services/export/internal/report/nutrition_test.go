package report

import (
	"reflect"
	"testing"
)

func TestNutritionTablesRespectBlockWeekAndIgnoreInvalidData(t *testing.T) {
	meta := map[string]any{"current_block_id": "demo", "blocks": []any{map[string]any{"id": "demo", "week_start_day": "Thursday"}}}
	notes := []map[string]any{
		{"date": "2026-11-06", "avg_protein_g": 170.0, "avg_sleep_hours": 7.5, "consistent": true, "water_unit": "L"},
		{"date": "2026-11-07", "avg_protein_g": 190.0, "consistent": false},
		{"date": "2026-11-13", "avg_protein_g": 200.0, "consistent": true},
		{"date": "bad", "avg_protein_g": 500.0},
	}
	tables := NutritionTables(notes, meta)
	if len(tables) != 2 {
		t.Fatalf("got %d tables", len(tables))
	}
	want := []any{"2026-11-05", nil, 180.0, nil, nil, 7.5, nil, 50.0, "L"}
	if !reflect.DeepEqual(tables[1].Rows[0], want) {
		t.Fatalf("got %#v, want %#v", tables[1].Rows[0], want)
	}
	if got := tables[0].Rows[0]; !reflect.DeepEqual(got, []any{"Protein (g)", 186.7, 20.0}) {
		t.Fatalf("summary %#v", got)
	}
}

func TestNutritionTablesWithoutValidDates(t *testing.T) {
	if got := NutritionTables([]map[string]any{{"date": "invalid"}}, nil); len(got) != 0 {
		t.Fatal(got)
	}
}
