package workbook

import (
	"sort"
	"strings"

	"powerlifting/export/internal/calc"
	"powerlifting/export/internal/liftprofile"
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
)

func dots(total, bodyweight any, sex string) any {
	lift, ok1 := values.Float(total)
	weight, ok2 := values.Float(bodyweight)
	if !ok1 || !ok2 || lift <= 0 || weight <= 0 {
		return ""
	}
	result, err := calc.Dots(lift, weight, sex)
	if err != nil {
		return ""
	}
	return result
}

func liftTotal(lifts map[string]any) any {
	if values.Truthy(lifts["total_kg"]) {
		return lifts["total_kg"]
	}
	total := 0.0
	for _, key := range []string{"squat_kg", "bench_kg", "deadlift_kg"} {
		value, ok := values.Float(lifts[key])
		if !ok {
			return ""
		}
		total += value
	}
	return total
}

func extraTables(program, weekly map[string]any, export Context) []report.Table {
	meta, _ := program["meta"].(map[string]any)
	sex := values.Str2(meta["sex"])
	if sex == "" {
		sex = "male"
	}
	goalRows := [][]any{}
	for _, goal := range maps(program["goals"]) {
		goalRows = append(goalRows, []any{goal["title"], goal["type"], goal["priority"], goal["strategy"], goal["target_date"], goal["competition"], goal["federation"], goal["standard"], goal["target_total"], goal["target_dots"], goal["target_ipf_gl"], goal["weight_class_kg"], goal["acceptable_weight_classes"], goal["risk"], goal["notes"]})
	}
	federationRows := [][]any{}
	for _, federation := range maps(export.Federations["federations"]) {
		federationRows = append(federationRows, []any{"Federation", federation["name"], federation["abbreviation"], federation["region"], federation["status"], federation["notes"]})
	}
	for _, standard := range maps(export.Federations["qualification_standards"]) {
		federationRows = append(federationRows, []any{"Standard", standard["name"], standard["federation_id"], standard["weight_class_kg"], standard["total_kg"], standard})
	}
	historyRows := [][]any{}
	for _, entry := range export.MaxHistory {
		weight := entry["bodyweight_kg"]
		if !values.Truthy(weight) {
			weight = meta["current_body_weight_kg"]
		}
		historyRows = append(historyRows, []any{entry["date"], entry["squat_kg"], entry["bench_kg"], entry["deadlift_kg"], entry["total_kg"], weight, dots(entry["total_kg"], weight, sex), entry["context"]})
	}
	competitionRows := [][]any{}
	for _, entry := range maps(program["competitions"]) {
		targets, _ := entry["targets"].(map[string]any)
		results, _ := entry["results"].(map[string]any)
		weight := entry["body_weight_kg"]
		source := "competition"
		if !values.Truthy(weight) {
			weight = meta["current_body_weight_kg"]
			source = "program"
		}
		targetTotal, resultTotal := liftTotal(targets), liftTotal(results)
		var resultDots any
		if entry["status"] == "completed" {
			resultDots = dots(resultTotal, weight, sex)
		}
		competitionRows = append(competitionRows, []any{entry["name"], entry["date"], entry["status"], entry["federation"], entry["counts_toward_federation_ids"], entry["location"], entry["hotel_required"], entry["weight_class_kg"], weight, source, targets["squat_kg"], targets["bench_kg"], targets["deadlift_kg"], targetTotal, dots(targetTotal, weight, sex), results["squat_kg"], results["bench_kg"], results["deadlift_kg"], resultTotal, resultDots, entry["place"], entry["decision_date"], entry["projection_snapshot_date"], entry["notes"], entry["post_meet_report"], entry["between_comp_plan"], entry["comp_day_protocol"]})
	}
	weights := append([]map[string]any{}, export.WeightLog...)
	sort.SliceStable(weights, func(i, j int) bool { return values.Str2(weights[i]["date"]) < values.Str2(weights[j]["date"]) })
	weightRows := [][]any{}
	var previous float64
	hasPrevious := false
	for _, entry := range weights {
		kg, ok := values.Float(entry["kg"])
		var delta any
		if ok && hasPrevious {
			delta = calc.Round(kg-previous, 1)
		}
		if ok {
			previous, hasPrevious = kg, true
		}
		weightRows = append(weightRows, []any{entry["date"], entry["kg"], delta, entry["notes"]})
	}
	profileRows := [][]any{}
	for _, profile := range maps(program["lift_profiles"]) {
		lift := values.Str2(profile["lift"])
		options, _ := profile["options"].(map[string]any)
		profileRows = append(profileRows, []any{lift, liftprofile.TechniqueText(lift, options), profile["notes"], profile["volume_tolerance"], profile["stimulus_coefficient"], profile["stimulus_coefficient_reasoning"], profile["stimulus_coefficient_confidence"], profile["stimulus_coefficient_updated_at"]})
	}
	glossaryRows := [][]any{}
	for _, exercise := range export.Glossary {
		fatigue, _ := exercise["fatigue_profile"].(map[string]any)
		e1rm, _ := exercise["e1rm_estimate"].(map[string]any)
		glossaryRows = append(glossaryRows, []any{exercise["id"], exercise["name"], exercise["category"], exercise["fatigue_category"], exercise["primary_muscles"], exercise["secondary_muscles"], exercise["tertiary_muscles"], exercise["equipment"], exercise["description"], exercise["how_to_perform"], exercise["why_do_it"], exercise["video_url"], fatigue["axial"], fatigue["neural"], fatigue["peripheral"], fatigue["systemic"], exercise["fatigue_profile_source"], exercise["fatigue_reasoning"], e1rm["value_kg"], e1rm["method"], e1rm["basis"], e1rm["confidence"], e1rm["updated_at"], exercise["archived"]})
	}
	weeklyRows := [][]any{}
	for _, key := range []string{"week", "block", "sessions_analyzed", "fatigue_index", "readiness_score", "current_maxes", "compliance", "flags"} {
		if value, ok := weekly[key]; ok {
			weeklyRows = append(weeklyRows, []any{key, value})
		}
	}
	liftRows := [][]any{}
	lifts, _ := weekly["lifts"].(map[string]any)
	liftKeys := make([]string, 0, len(lifts))
	for key := range lifts {
		liftKeys = append(liftKeys, key)
	}
	sort.Strings(liftKeys)
	for _, name := range liftKeys {
		lift, _ := lifts[name].(map[string]any)
		liftRows = append(liftRows, []any{name, lift["progression_rate_kg_per_week"], lift["fit_quality"], lift["kendall_tau"], lift["volume_change_pct"], lift["intensity_change_pct"], lift["failed_sets"], lift["rpe_trend"]})
	}
	missing := "Not yet generated — open the Analysis page and let the report render before exporting."
	reportRows := func(value map[string]any) [][]any {
		if len(value) == 0 {
			return [][]any{{"Status", missing}}
		}
		keys := make([]string, 0, len(value))
		for key := range value {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		rows := [][]any{}
		for _, key := range keys {
			rows = append(rows, []any{strings.ReplaceAll(key, "_", " "), value[key]})
		}
		return rows
	}
	return []report.Table{
		{Title: "Goals", Headers: []string{"Title", "Type", "Priority", "Strategy", "Target Date", "Competition", "Federation", "Standard", "Target Total", "Target DOTS", "Target IPF GL", "Target Weight Class", "Acceptable Classes", "Risk", "Notes"}, Rows: goalRows},
		{Title: "Federation Standards", Headers: []string{"Type", "Name", "Federation", "Region or Weight Class", "Status or Total", "Details"}, Rows: federationRows},
		{Title: "Max History", Headers: []string{"Date", "Squat", "Bench", "Deadlift", "Total", "Bodyweight", "DOTS", "Context"}, Rows: historyRows},
		{Title: "Competitions", Headers: []string{"Name", "Date", "Status", "Federation", "Counts Toward", "Location", "Hotel Required", "Weight Class", "Body Weight", "Body Weight Source", "Target Squat", "Target Bench", "Target Deadlift", "Target Total", "Target DOTS", "Result Squat", "Result Bench", "Result Deadlift", "Result Total", "Result DOTS", "Place", "Decision Date", "Projection Snapshot Date", "Notes", "Post-Meet Report", "Between Comp Plan", "Comp Day Protocol"}, Rows: competitionRows},
		{Title: "Weight Log", Headers: []string{"Date", "Kg", "Delta From Previous", "Notes"}, Rows: weightRows},
		{Title: "Lift Profiles", Headers: []string{"Lift", "Technique", "Notes", "Volume Tolerance", "Stimulus Coefficient", "Coefficient Reasoning", "Confidence", "Updated At"}, Rows: profileRows},
		{Title: "Exercise Glossary", Headers: []string{"ID", "Name", "Category", "Fatigue Category", "Primary Muscles", "Secondary Muscles", "Tertiary Muscles", "Equipment", "Description", "How To Perform", "Why Do It", "Video URL", "Fatigue Axial", "Fatigue Neural", "Fatigue Peripheral", "Fatigue Systemic", "Fatigue Source", "Fatigue Reasoning", "E1RM Value", "E1RM Method", "E1RM Basis", "E1RM Confidence", "E1RM Updated At", "Archived"}, Rows: glossaryRows},
		{Title: "Weekly Analysis", Headers: []string{"Field", "Value"}, Rows: weeklyRows},
		{Title: "Per-Lift Metrics", Headers: []string{"Lift", "Progression (kg/wk)", "Fit Quality", "Kendall τ", "Volume Change %", "Intensity Change %", "Failed Sets", "RPE Trend"}, Rows: liftRows},
		{Title: "ROI Correlation", Headers: []string{"Field", "Value"}, Rows: reportRows(export.Correlation)},
		{Title: "Program Evaluation", Headers: []string{"Field", "Value"}, Rows: reportRows(export.Evaluation)},
	}
}
