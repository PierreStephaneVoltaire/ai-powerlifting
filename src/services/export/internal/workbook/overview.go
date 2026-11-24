package workbook

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
)

func first(items ...any) any {
	for _, item := range items {
		if item != nil && item != "" {
			return item
		}
	}
	return ""
}

func serialized(value any, fallback any) string {
	if value == nil {
		value = fallback
	}
	data, _ := json.Marshal(value)
	return string(data)
}

func metadataRows(meta, program map[string]any, context Context) [][]any {
	creator := first(meta["creator"], context.PK, program["pk"], "operator")
	pk := first(context.PK, program["pk"], creator)
	version := first(context.Version, meta["version"], meta["version_label"])
	if number, ok := values.Float(version); ok && number >= 0 {
		version = fmt.Sprintf("v%03d", int(number))
	}
	sex := strings.ToLower(values.Str2(first(meta["sex"], "male")))
	today := time.Now().UTC().Format("2006-01-02")
	competition := ""
	for _, item := range maps(program["competitions"]) {
		date := values.Str2(first(item["date"], item["start_date"]))
		status := first(item["status"], item["user_status"])
		if status == "confirmed" && date > today && (competition == "" || date < competition) {
			competition = date
		}
	}
	pct, _ := meta["attempt_pct"].(map[string]any)
	notes := meta["training_notes"]
	if notes == nil {
		notes = []any{}
	}
	if _, ok := notes.([]any); ok {
		notes = serialized(notes, []any{})
	}
	return [][]any{
		{"Program Name", meta["program_name"]}, {"Creator", creator}, {"Program PK", pk}, {"Program Version Token", version},
		{"Version Label", meta["version_label"]}, {"Sex", sex}, {"Program Start", meta["program_start"]}, {"Competition Date", competition},
		{"Federation", meta["federation"]}, {"Practicing For", meta["practicing_for"]}, {"Weight Class (kg)", meta["weight_class_kg"]}, {"Weight Class Confirm By", meta["weight_class_confirm_by"]},
		{"Current Body Weight (kg)", first(meta["current_body_weight_kg"], meta["bodyweight_kg"])}, {"Current Body Weight (lb)", meta["current_body_weight_lb"]},
		{"Target Squat (kg)", meta["target_squat_kg"]}, {"Target Bench (kg)", meta["target_bench_kg"]}, {"Target Deadlift (kg)", meta["target_dl_kg"]}, {"Target Total (kg)", meta["target_total_kg"]},
		{"Attempt Pct - Opener", pct["opener"]}, {"Attempt Pct - Second", pct["second"]}, {"Attempt Pct - Third", pct["third"]},
		{"Height (cm)", meta["height_cm"]}, {"Arm Wingspan (cm)", meta["arm_wingspan_cm"]}, {"Leg Length (cm)", meta["leg_length_cm"]}, {"Equipment", meta["equipment"]},
		{"Archived", meta["archived"]}, {"Archived At", meta["archived_at"]}, {"Last Updated", meta["updated_at"]}, {"Training Notes", notes}, {"Change Log", serialized(meta["change_log"], []any{})},
	}
}

func federationTable(library map[string]any) report.Table {
	federations := maps(library["federations"])
	standards := maps(library["qualification_standards"])
	names := map[string]any{}
	rows := [][]any{{"Federations"}, {"Name", "Abbreviation", "Region", "Status", "Notes"}}
	for _, item := range federations {
		names[values.Str2(item["id"])] = first(item["abbreviation"], item["name"])
		rows = append(rows, []any{item["name"], item["abbreviation"], item["region"], item["status"], item["notes"]})
	}
	if len(federations) == 0 {
		rows = append(rows, []any{"No federations recorded."})
	}
	rows = append(rows, nil, nil, []any{"Qualification Standards"}, []any{"Federation", "Competition", "Season", "Sex", "Equipment", "Event", "Age Class", "Division", "Weight Class", "Required Total", "Qualifying Start", "Qualifying End", "Source Label", "Source URL", "Status"})
	sort.SliceStable(standards, func(i, j int) bool {
		a, b := standards[i], standards[j]
		if a["status"] != b["status"] {
			return values.Str2(a["status"]) < values.Str2(b["status"])
		}
		ay, _ := values.Float(a["season_year"])
		by, _ := values.Float(b["season_year"])
		if ay != by {
			return ay > by
		}
		aw, _ := values.Float(a["weight_class_kg"])
		bw, _ := values.Float(b["weight_class_kg"])
		return aw < bw
	})
	for _, item := range standards {
		rows = append(rows, []any{names[values.Str2(item["federation_id"])], item["competition_name"], item["season_year"], item["sex"], item["equipment"], item["event"], item["age_class"], item["division"], item["weight_class_kg"], item["required_total_kg"], item["qualifying_start_date"], item["qualifying_end_date"], item["source_label"], item["source_url"], item["status"]})
	}
	if len(standards) == 0 {
		rows = append(rows, []any{"No qualification standards recorded."})
	}
	return report.Table{Title: "Federation Standards", Rows: rows}
}

func goalTable(meta map[string]any, goals, competitions []map[string]any, sex string, library map[string]any) report.Table {
	weight := first(meta["current_body_weight_kg"], meta["bodyweight_kg"])
	total := liftTotal(map[string]any{"total_kg": meta["target_total_kg"], "squat_kg": meta["target_squat_kg"], "bench_kg": meta["target_bench_kg"], "deadlift_kg": meta["target_dl_kg"]})
	primary := []string{}
	for _, goal := range goals {
		if goal["priority"] == "primary" {
			primary = append(primary, values.Str2(goal["title"]))
		}
	}
	rows := [][]any{{"Program Name", meta["program_name"]}, {"Explicit Goals Recorded", len(goals)}, {"Primary Goals", strings.Join(primary, ", ")}, {"Current Weight Class (kg)", meta["weight_class_kg"]}, {"Current Body Weight (kg)", weight}, {"Program Target Total (kg)", total}, {"Program Target DOTS", dots(total, weight, sex)}, {"Attempt Pct", serialized(meta["attempt_pct"], map[string]any{})}, nil, {"Explicit Goals"}, {"Title", "Type", "Priority", "Strategy", "Target Date", "Competition", "Federation", "Standard", "Target Total", "Target DOTS", "Target IPF GL", "Target Weight Class", "Acceptable Classes", "Risk", "Notes"}}
	federations := map[string]map[string]any{}
	standards := map[string]map[string]any{}
	competitionsByDate := map[string]map[string]any{}
	for _, item := range maps(library["federations"]) {
		federations[values.Str2(item["id"])] = item
	}
	for _, item := range maps(library["qualification_standards"]) {
		standards[values.Str2(item["id"])] = item
	}
	for _, item := range competitions {
		competitionsByDate[values.Str2(item["date"])] = item
	}
	goals = append([]map[string]any{}, goals...)
	order := map[string]int{"primary": 0, "secondary": 1, "optional": 2}
	sort.SliceStable(goals, func(i, j int) bool {
		a, ok := order[values.Str2(goals[i]["priority"])]
		if !ok {
			a = 9
		}
		b, ok := order[values.Str2(goals[j]["priority"])]
		if !ok {
			b = 9
		}
		if a != b {
			return a < b
		}
		return values.Str2(goals[i]["target_date"]) < values.Str2(goals[j]["target_date"])
	})
	for _, goal := range goals {
		targetStandards, _ := goal["target_standard_ids"].([]any)
		var linked []map[string]any
		for _, id := range targetStandards {
			if std := standards[values.Str2(id)]; std != nil {
				linked = append(linked, std)
			}
		}
		var standard map[string]any
		if len(linked) > 0 {
			standard = linked[0]
		}
		fed := federations[values.Str2(goal["target_federation_id"])]
		if fed == nil {
			fed = federations[values.Str2(standard["federation_id"])]
		}
		dates, _ := goal["target_competition_dates"].([]any)
		var dateNames, meetNames, labels []string
		for _, date := range dates {
			d := values.Str2(date)
			dateNames = append(dateNames, d)
			if meet := competitionsByDate[d]; meet != nil && meet["name"] != nil {
				meetNames = append(meetNames, values.Str2(meet["name"]))
			}
		}
		for _, std := range linked {
			labels = append(labels, fmt.Sprintf("%v %vkg %vkg", first(std["season_year"]), first(std["weight_class_kg"]), first(std["required_total_kg"])))
		}
		rows = append(rows, []any{goal["title"], goal["goal_type"], goal["priority"], goal["strategy_mode"], first(goal["target_date"], strings.Join(dateNames, ", ")), strings.Join(meetNames, ", "), first(fed["abbreviation"], fed["name"]), strings.Join(labels, "; "), first(goal["target_total_kg"], standard["required_total_kg"]), goal["target_dots"], goal["target_ipf_gl"], first(goal["target_weight_class_kg"], standard["weight_class_kg"]), serialized(goal["acceptable_weight_classes_kg"], []any{}), goal["risk_tolerance"], goal["notes"]})
	}
	if len(goals) == 0 {
		rows = append(rows, []any{"No explicit goals recorded. Program targets are shown in the header rows."})
	}
	rows = append(rows, nil, nil, []any{"Competition Targets"}, []any{"Name", "Date", "Status", "Host Federation", "Counts Toward", "Weight Class", "Body Weight", "Target Squat", "Target Bench", "Target Deadlift", "Target Total", "Target DOTS", "Notes"})
	competitions = append([]map[string]any{}, competitions...)
	sort.SliceStable(competitions, func(i, j int) bool {
		return values.Str2(competitions[i]["date"]) < values.Str2(competitions[j]["date"])
	})
	for _, comp := range competitions {
		targets, _ := comp["targets"].(map[string]any)
		fed := federations[values.Str2(comp["federation_id"])]
		counted, _ := comp["counts_toward_federation_ids"].([]any)
		labels := []string{}
		for _, id := range counted {
			f := federations[values.Str2(id)]
			labels = append(labels, values.Str2(first(f["abbreviation"], f["name"], id)))
		}
		bw := first(comp["body_weight_kg"], weight, float64(0))
		t := liftTotal(targets)
		rows = append(rows, []any{comp["name"], comp["date"], comp["status"], first(fed["abbreviation"], fed["name"], comp["federation"]), strings.Join(labels, ", "), comp["weight_class_kg"], bw, targets["squat_kg"], targets["bench_kg"], targets["deadlift_kg"], t, dots(t, bw, sex), comp["notes"]})
	}
	if len(competitions) == 0 {
		rows = append(rows, []any{"No competitions recorded."})
	}
	return report.Table{Title: "Goals", Rows: rows}
}
