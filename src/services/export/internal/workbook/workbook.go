package workbook

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/xuri/excelize/v2"
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
)

func maps(value any) []map[string]any {
	list, _ := value.([]any)
	out := make([]map[string]any, 0, len(list))
	for _, raw := range list {
		if item, ok := raw.(map[string]any); ok {
			out = append(out, item)
		}
	}
	return out
}

func failureReasons(value any) string {
	labels := map[string]string{"strength_failure": "Strength failure", "technical_failure": "Technical failure", "command_failure": "Command failure", "grip": "Grip", "depth": "Depth", "pause": "Pause", "lockout": "Lockout", "balance": "Balance", "pain": "Pain", "fatigue": "Fatigue", "misload_bad_attempt_selection": "Misload / bad attempt selection"}
	sets, ok := value.([]any)
	if !ok {
		return ""
	}
	chunks := []string{}
	for index, raw := range sets {
		reasons, ok := raw.([]any)
		if !ok {
			continue
		}
		values := []string{}
		for _, reason := range reasons {
			if text, ok := reason.(string); ok && labels[text] != "" {
				values = append(values, labels[text])
			}
		}
		if len(values) > 0 {
			chunks = append(chunks, fmt.Sprintf("set %d: %s", index+1, strings.Join(values, ", ")))
		}
	}
	return strings.Join(chunks, "; ")
}

func rowsForSessions(sessions []map[string]any) ([][]any, [][]any, [][]any) {
	sessionRows, plannedRows, actualRows := [][]any{}, [][]any{}, [][]any{}
	for _, session := range sessions {
		wellness, _ := session["wellness"].(map[string]any)
		sessionRows = append(sessionRows, []any{session["id"], session["date"], session["week"], session["week_number"], session["block"], session["phase_name"], session["day"], session["status"], session["completed"], session["body_weight_kg"], session["body_weight_source"], session["session_rpe"], wellness["sleep"], wellness["soreness"], wellness["mood"], wellness["stress"], wellness["energy"], wellness["recorded_at"], session["session_notes"]})
		for _, ex := range maps(session["planned_exercises"]) {
			plannedRows = append(plannedRows, []any{session["date"], session["week_number"], session["block"], session["phase_name"], ex["name"], ex["sets"], ex["reps"], ex["kg"], ex["load_source"], ex["rpe_target"], ex["notes"], session["status"]})
		}
		for _, ex := range maps(session["exercises"]) {
			sets, _ := values.Float(ex["sets"])
			reps, _ := values.Float(ex["reps"])
			kg, _ := values.Float(ex["kg"])
			var failed bool
			status, _ := ex["set_statuses"].([]any)
			statuses := make([]string, len(status))
			for i, v := range status {
				if v == "failed" {
					failed = true
					statuses[i] = "1"
				} else {
					statuses[i] = "0"
				}
			}
			actualRows = append(actualRows, []any{session["date"], session["week_number"], session["block"], session["phase_name"], ex["name"], ex["sets"], ex["reps"], ex["kg"], failed, strings.Join(statuses, "; "), failureReasons(ex["failed_set_reasons"]), ex["rpe"], ex["notes"], math.Round(sets*reps*kg*10) / 10, session["status"]})
		}
	}
	return sessionRows, plannedRows, actualRows
}

func flattenRows(source, path string, value any, rows *[][]any) {
	switch item := value.(type) {
	case map[string]any:
		keys := make([]string, 0, len(item))
		for key := range item {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			next := key
			if path != "" {
				next = path + "." + key
			}
			flattenRows(source, next, item[key], rows)
		}
	case []any:
		for i, element := range item {
			flattenRows(source, fmt.Sprintf("%s[%d]", path, i), element, rows)
		}
	case []map[string]any:
		for i, element := range item {
			flattenRows(source, fmt.Sprintf("%s[%d]", path, i), element, rows)
		}
	default:
		if path == "" {
			path = "(root)"
		}
		if text, ok := value.(string); ok {
			value = truncate(text)
		}
		if flag, ok := value.(bool); ok {
			if flag {
				value = "Yes"
			} else {
				value = "No"
			}
		}
		*rows = append(*rows, []any{source, path, value})
	}
}

type Context struct {
	WeightLog   []map[string]any
	MaxHistory  []map[string]any
	Federations map[string]any
	Glossary    []map[string]any
	Correlation map[string]any
	Evaluation  map[string]any
}

func truncate(value string) string {
	characters := []rune(value)
	if len(characters) > 32000 {
		return string(characters[:31970]) + "... [truncated]"
	}
	return value
}

func Render(program, weekly map[string]any, options ...Context) ([]byte, error) {
	var export Context
	if len(options) > 0 {
		export = options[0]
	}
	book := excelize.NewFile()
	defer book.Close()
	headerStyle, err := book.NewStyle(&excelize.Style{Font: &excelize.Font{Bold: true, Size: 11}, Fill: excelize.Fill{Type: "pattern", Pattern: 1, Color: []string{"D9D9D9"}}, Alignment: &excelize.Alignment{WrapText: true, Vertical: "top"}})
	if err != nil {
		return nil, err
	}
	if err := book.DeleteSheet("Sheet1"); err != nil {
		return nil, err
	}
	add := func(title string, headers []string, rows [][]any) error {
		if _, err := book.NewSheet(title); err != nil {
			return err
		}
		all := make([][]any, 0, len(rows)+1)
		header := make([]any, len(headers))
		for i, v := range headers {
			header[i] = v
		}
		if headers != nil {
			all = append(all, header)
		}
		all = append(all, rows...)
		widthCount := len(headers)
		if headers == nil {
			for _, row := range rows {
				widthCount = max(widthCount, len(row))
			}
		}
		widths := make([]int, widthCount)
		for i, row := range all {
			for j, value := range row {
				if value == nil {
					continue
				}
				cell, err := excelize.CoordinatesToCellName(j+1, i+1)
				if err != nil {
					return err
				}
				switch value.(type) {
				case string, float32, float64, int, int32, int64, bool:
				default:
					data, e := json.Marshal(value)
					if e != nil {
						return e
					}
					value = string(data)
				}
				if text, ok := value.(string); ok {
					value = truncate(text)
				}
				if err = book.SetCellValue(title, cell, value); err != nil {
					return fmt.Errorf("%s %s: %w", title, cell, err)
				}
				if j < len(widths) {
					widths[j] = max(widths[j], len([]rune(fmt.Sprint(value))))
				}
			}
		}
		if len(headers) > 0 {
			last, err := excelize.CoordinatesToCellName(len(headers), 1)
			if err != nil {
				return err
			}
			if err = book.SetCellStyle(title, "A1", last, headerStyle); err != nil {
				return err
			}
			if err = book.SetPanes(title, &excelize.Panes{Freeze: true, YSplit: 1, TopLeftCell: "A2", ActivePane: "bottomLeft"}); err != nil {
				return err
			}
			for i, width := range widths {
				column, err := excelize.ColumnNumberToName(i + 1)
				if err != nil {
					return err
				}
				if err = book.SetColWidth(title, column, column, float64(min(width+2, 50))); err != nil {
					return err
				}
			}
		} else {
			for i, width := range widths {
				column, err := excelize.ColumnNumberToName(i + 1)
				if err != nil {
					return err
				}
				if err = book.SetColWidth(title, column, column, float64(min(max(width, 10)+2, 60))); err != nil {
					return err
				}
			}
		}
		return nil
	}
	rawSessions, _ := program["sessions"].([]any)
	sessions := maps(report.ExpandSessionSets(rawSessions))
	sessionsRows, plannedRows, actualRows := rowsForSessions(sessions)
	meta, _ := program["meta"].(map[string]any)
	metaRows := [][]any{}
	for _, item := range []struct{ label, key string }{{"Program Name", "program_name"}, {"Creator", "creator"}, {"Program PK", "pk"}, {"Program Version Token", "version"}, {"Version Label", "version_label"}, {"Sex", "sex"}, {"Program Start", "program_start"}, {"Federation", "federation"}, {"Practicing For", "practicing_for"}, {"Weight Class (kg)", "weight_class_kg"}, {"Current Body Weight (kg)", "current_body_weight_kg"}, {"Target Squat (kg)", "target_squat_kg"}, {"Target Bench (kg)", "target_bench_kg"}, {"Target Deadlift (kg)", "target_dl_kg"}, {"Target Total (kg)", "target_total_kg"}, {"Height (cm)", "height_cm"}, {"Arm Wingspan (cm)", "arm_wingspan_cm"}, {"Leg Length (cm)", "leg_length_cm"}, {"Equipment", "equipment"}, {"Training Notes", "training_notes"}} {
		metaRows = append(metaRows, []any{item.label, meta[item.key]})
	}
	phaseRows := [][]any{}
	for _, phase := range maps(program["phases"]) {
		block := phase["block"]
		if block == nil || block == "" {
			block = "current"
		}
		phaseRows = append(phaseRows, []any{phase["name"], block, phase["start_week"], phase["end_week"], phase["intent"], phase["target_rpe_min"], phase["target_rpe_max"], phase["days_per_week"], phase["notes"]})
	}
	biometrics := [][]any{}
	for _, note := range maps(program["diet_notes"]) {
		biometrics = append(biometrics, []any{note["date"], note["notes"], note["avg_daily_calories"], note["avg_protein_g"], note["avg_carb_g"], note["avg_fat_g"], note["avg_sleep_hours"], note["water_intake"], note["water_unit"], note["consistent"]})
	}
	supplements := [][]any{}
	for _, item := range maps(program["supplements"]) {
		supplements = append(supplements, []any{item["name"], item["dose"]})
	}
	maxes := [][]any{}
	currentMaxes, _ := program["current_maxes"].(map[string]any)
	keys := make([]string, 0, len(currentMaxes))
	for key := range currentMaxes {
		if key != "_note" && key != "" {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	for _, key := range keys {
		maxes = append(maxes, []any{strings.ToUpper(key[:1]) + strings.ReplaceAll(key[1:], "_", " "), currentMaxes[key]})
	}
	phaseSupplementRows := [][]any{}
	for _, phase := range maps(program["supplement_phases"]) {
		items := maps(phase["items"])
		if len(items) == 0 {
			items = []map[string]any{{}}
		}
		for _, item := range items {
			phaseSupplementRows = append(phaseSupplementRows, []any{phase["phase"], phase["phase_name"], phase["block"], phase["start_week"], phase["end_week"], item["name"], item["dose"], item["notes"], phase["notes"], phase["peak_week_protocol"]})
		}
	}
	videos, notes := [][]any{}, [][]any{}
	for _, session := range sessions {
		for _, video := range maps(session["videos"]) {
			videos = append(videos, []any{session["date"], session["block"], video["exercise_name"], video["set_number"], video["notes"], video["uploaded_at"], video["s3_key"], video["thumbnail_s3_key"], video["thumbnail_status"]})
		}
		if text, ok := session["session_notes"].(string); ok && text != "" {
			notes = append(notes, []any{"Session", session["date"], session["day"], text})
		}
	}
	if raw, ok := meta["training_notes"].([]any); ok {
		for _, note := range raw {
			notes = append(notes, []any{"Meta", meta["updated_at"], "Training Note", note})
		}
	}
	for _, note := range maps(meta["block_notes"]) {
		if text, ok := note["notes"].(string); ok && text != "" {
			date := note["date"]
			if date == nil || date == "" {
				date = note["updated_at"]
			}
			notes = append(notes, []any{"Program", date, "Dated Program Note", text})
		}
	}
	for _, phase := range maps(program["phases"]) {
		if text, ok := phase["notes"].(string); ok && text != "" {
			notes = append(notes, []any{"Phase", fmt.Sprintf("W%v-W%v", phase["start_week"], phase["end_week"]), phase["name"], text})
		}
	}
	for _, comp := range maps(program["competitions"]) {
		if text, ok := comp["notes"].(string); ok && text != "" {
			notes = append(notes, []any{"Competition", comp["date"], comp["name"], text})
		}
	}
	for _, note := range maps(program["diet_notes"]) {
		if text, ok := note["notes"].(string); ok && text != "" {
			notes = append(notes, []any{"Biometrics", note["date"], "Diet Note", text})
		}
	}
	for _, phase := range maps(program["supplement_phases"]) {
		if text, ok := phase["notes"].(string); ok && text != "" {
			notes = append(notes, []any{"Supplement Phase", phase["phase_name"], fmt.Sprintf("Phase %v", phase["phase"]), text})
		}
		for _, item := range maps(phase["items"]) {
			if text, ok := item["notes"].(string); ok && text != "" {
				notes = append(notes, []any{"Supplement Item", phase["phase_name"], item["name"], text})
			}
		}
	}
	if len(sessionsRows) == 0 {
		sessionsRows = append(sessionsRows, []any{"—", "", "", "", "", "", "", "No sessions recorded"})
	}
	if len(plannedRows) == 0 {
		plannedRows = append(plannedRows, []any{"—", "", "", "", "No planned exercises recorded"})
	}
	if len(actualRows) == 0 {
		actualRows = append(actualRows, []any{"—", "", "", "", "No exercises recorded"})
	}
	if len(phaseRows) == 0 {
		phaseRows = append(phaseRows, []any{"—", "current", "", "", "No phases recorded"})
	}
	if len(videos) == 0 {
		videos = append(videos, []any{"—", "", "No videos recorded"})
	}
	if len(notes) == 0 {
		notes = append(notes, []any{"—", "", "No notes recorded", ""})
	}
	preferences := program["operator_prefs"]
	if preferences == nil {
		preferences = map[string]any{}
	}
	breaks := program["breaks"]
	if breaks == nil {
		breaks = []any{}
	}
	for _, table := range []report.Table{
		{Title: "Breaks & Prefs", Headers: []string{"Field", "Value"}, Rows: [][]any{{"Archived", meta["archived"]}, {"Archived At", meta["archived_at"]}, {"Operator Prefs", preferences}, {"Breaks", breaks}}},
		{Title: "Videos", Headers: []string{"Session Date", "Block", "Exercise", "Set #", "Notes", "Uploaded At", "Video Key", "Thumbnail Key", "Thumbnail Status"}, Rows: videos},
		{Title: "Notes", Headers: []string{"Source", "Date", "Title", "Notes"}, Rows: notes},
		{Title: "Current Maxes", Headers: []string{"Lift", "Current Max (kg)"}, Rows: maxes},
		{Title: "Supplement Phases", Headers: []string{"Phase", "Phase Name", "Block", "Start Week", "End Week", "Supplement", "Dose", "Item Notes", "Phase Notes", "Peak Week Protocol"}, Rows: phaseSupplementRows},
		{Title: "Meta", Headers: []string{"Field", "Value"}, Rows: metaRows},
		{Title: "Phases", Headers: []string{"Phase", "Block", "Start Week", "End Week", "Intent", "Target RPE Min", "Target RPE Max", "Days/Week", "Notes"}, Rows: phaseRows},
		{Title: "Biometrics", Headers: []string{"Date", "Notes", "Calories", "Protein (g)", "Carbs (g)", "Fat (g)", "Sleep (hrs)", "Water", "Water Unit", "Consistent"}, Rows: biometrics},
		{Title: "Supplements", Headers: []string{"Name", "Dose"}, Rows: supplements},
		{Title: "Sessions", Headers: []string{"ID", "Date", "Week", "Week #", "Block", "Phase", "Day", "Status", "Completed", "Body Weight (kg)", "Body Weight Source", "Session RPE", "Sleep", "Soreness", "Mood", "Stress", "Energy", "Wellness Recorded At", "Notes"}, Rows: sessionsRows},
		{Title: "Planned Exercises", Headers: []string{"Date", "Week", "Block", "Phase", "Exercise", "Sets", "Reps", "Weight (kg)", "Load Source", "RPE Target", "Notes", "Session Status"}, Rows: plannedRows},
		{Title: "Exercises", Headers: []string{"Date", "Week", "Block", "Phase", "Exercise", "Sets", "Reps", "Weight (kg)", "Failed", "Failed Sets", "Failed Set Reasons", "RPE", "Notes", "Volume", "Session Status"}, Rows: actualRows},
	} {
		if err := add(table.Title, table.Headers, table.Rows); err != nil {
			return nil, err
		}
	}
	for _, table := range extraTables(program, weekly, export) {
		if err := add(table.Title, table.Headers, table.Rows); err != nil {
			return nil, err
		}
	}
	for _, table := range report.AnalysisTables(weekly, maps(program["diet_notes"]), meta) {
		if err := add(table.Title, table.Headers, table.Rows); err != nil {
			return nil, err
		}
	}
	sex, _ := meta["sex"].(string)
	sex = strings.ToLower(sex)
	if sex == "" {
		sex = "male"
	}
	if err := add("Trends", nil, report.Trends(sessions, export.WeightLog, maps(program["diet_notes"]), sex)); err != nil {
		return nil, err
	}
	raw := [][]any{}
	flattenRows("program", "", program, &raw)
	flattenRows("analysis", "weekly", weekly, &raw)
	flattenRows("analysis", "correlation", export.Correlation, &raw)
	flattenRows("analysis", "program_evaluation", export.Evaluation, &raw)
	flattenRows("weight_log", "", export.WeightLog, &raw)
	flattenRows("max_history", "", export.MaxHistory, &raw)
	flattenRows("federation_library", "", export.Federations, &raw)
	flattenRows("glossary", "", export.Glossary, &raw)
	if len(raw) == 0 {
		raw = append(raw, []any{"—", "(empty)", ""})
	}
	if err := add("Raw Export", []string{"Source", "Path", "Value"}, raw); err != nil {
		return nil, err
	}
	var out bytes.Buffer
	if err := book.Write(&out); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}
