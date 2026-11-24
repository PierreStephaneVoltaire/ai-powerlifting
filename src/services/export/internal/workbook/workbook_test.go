package workbook

import (
	"bytes"
	"strings"
	"testing"

	"github.com/xuri/excelize/v2"
)

func TestWorkbookMarksTruncatedTextAndFormatsRawBooleans(t *testing.T) {
	program := map[string]any{"meta": map[string]any{"training_notes": strings.Repeat("x", 32001), "archived": true}}
	data, err := Render(program, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	rows, err := book.GetRows("Raw Export")
	if err != nil {
		t.Fatal(err)
	}
	seenBool, seenTruncation := false, false
	for _, row := range rows {
		if len(row) < 3 {
			continue
		}
		if row[1] == "meta.archived" {
			seenBool = row[2] == "Yes"
		}
		if row[1] == "meta.training_notes" {
			seenTruncation = strings.HasSuffix(row[2], "... [truncated]")
		}
	}
	if !seenBool || !seenTruncation {
		t.Fatalf("boolean=%v truncation=%v", seenBool, seenTruncation)
	}
}

func TestWorkbookKeepsPlannedAndActualLoadsSeparate(t *testing.T) {
	program := map[string]any{"sessions": []any{map[string]any{"date": "2026-11-16", "planned_exercises": []any{map[string]any{"name": "Squat", "kg": 100.0, "rpe_target": 8.0}}, "exercises": []any{map[string]any{"name": "Squat", "kg": 95.0, "rpe": 9.0}}}}, "meta": map[string]any{}}
	data, err := Render(program, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	style, err := book.GetCellStyle("Sessions", "A1")
	if err != nil || style == 0 {
		t.Fatalf("missing header style: %d, %v", style, err)
	}
	panes, err := book.GetPanes("Sessions")
	if err != nil || !panes.Freeze || panes.YSplit != 1 {
		t.Fatalf("missing frozen header: %#v, %v", panes, err)
	}
	for _, check := range []struct{ sheet, cell, want string }{{"Planned Exercises", "H2", "100"}, {"Planned Exercises", "J2", "8"}, {"Exercises", "H2", "95"}, {"Exercises", "L2", "9"}} {
		got, err := book.GetCellValue(check.sheet, check.cell)
		if err != nil || got != check.want {
			t.Errorf("%s %s = %q, %v", check.sheet, check.cell, got, err)
		}
	}
}

func TestWorkbookExpandsDifferentPerformedSets(t *testing.T) {
	program := map[string]any{"sessions": []any{map[string]any{"exercises": []any{map[string]any{"name": "Squat", "sets_data": []any{map[string]any{"kg": 95.0, "reps": 5.0, "rpe": 9.0}, map[string]any{"kg": 97.5, "reps": 5.0, "rpe": 9.5}}}}}}}
	data, err := Render(program, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	for _, check := range []struct{ cell, want string }{{"F2", "1"}, {"H2", "95"}, {"H3", "97.5"}, {"L3", "9.5"}, {"N3", "487.5"}} {
		got, err := book.GetCellValue("Exercises", check.cell)
		if err != nil || got != check.want {
			t.Errorf("%s = %q, %v", check.cell, got, err)
		}
	}
}

func TestWorkbookIncludesRawData(t *testing.T) {
	data, err := Render(map[string]any{"meta": map[string]any{"program_name": "Demo"}}, map[string]any{"fatigue_index": 0.3})
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	rows, err := book.GetRows("Raw Export")
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 3 || rows[1][1] != "meta.program_name" || rows[1][2] != "Demo" || rows[2][0] != "analysis" || rows[2][1] != "weekly.fatigue_index" {
		t.Fatalf("raw rows %#v", rows)
	}
}

func TestWorkbookIncludesBreaksAndPreferences(t *testing.T) {
	data, err := Render(map[string]any{"meta": map[string]any{"archived": true}, "operator_prefs": map[string]any{"units": "kg"}, "breaks": []any{map[string]any{"reason": "travel"}}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	for cell, want := range map[string]string{"B2": "TRUE", "B4": `{"units":"kg"}`, "B5": `[{"reason":"travel"}]`} {
		got, err := book.GetCellValue("Breaks & Prefs", cell)
		if err != nil || got != want {
			t.Errorf("%s = %q, %v", cell, got, err)
		}
	}
}

func TestWorkbookIncludesTrendSections(t *testing.T) {
	data, err := Render(map[string]any{"meta": map[string]any{}, "sessions": []any{}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	rows, err := book.GetRows("Trends")
	if err != nil || len(rows) < 6 || rows[0][0] != "Bodyweight Trend" || rows[1][0] != "Status" {
		t.Fatalf("trend rows %#v, %v", rows, err)
	}
}

func TestFailedSetsKeepReasons(t *testing.T) {
	program := map[string]any{"sessions": []any{map[string]any{"exercises": []any{map[string]any{"name": "Press", "set_statuses": []any{"completed", "failed"}, "failed_set_reasons": []any{[]any{}, []any{"strength_failure"}}, "sets_data": []any{map[string]any{"kg": 10.0}, map[string]any{"kg": 9.0}}}}}}}
	data, err := Render(program, nil)
	if err != nil {
		t.Fatal(err)
	}
	book, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer book.Close()
	for _, check := range []struct{ cell, want string }{{"I3", "TRUE"}, {"J3", "1"}, {"K3", "set 1: Strength failure"}} {
		got, err := book.GetCellValue("Exercises", check.cell)
		if err != nil || got != check.want {
			t.Errorf("%s = %q, %v", check.cell, got, err)
		}
	}
}
