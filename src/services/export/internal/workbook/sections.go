package workbook

import (
	"sort"
	"strings"

	"powerlifting/export/internal/calc"
	"powerlifting/export/internal/liftprofile"
	"powerlifting/export/internal/markdown"
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
	if !values.Blank(lifts["total_kg"]) {
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

func extraTables(program, weekly map[string]any, export Context, sessions []map[string]any) []report.Table {
	meta, _ := program["meta"].(map[string]any)
	sex := values.Str2(meta["sex"])
	if sex == "" {
		sex = "male"
	}

	historyRows := [][]any{}
	history := append([]map[string]any{}, export.MaxHistory...)
	sort.SliceStable(history, func(i, j int) bool { return values.Str2(history[i]["date"]) < values.Str2(history[j]["date"]) })
	for _, entry := range history {
		weight := first(entry["bodyweight_kg"], meta["current_body_weight_kg"], meta["bodyweight_kg"])
		total := first(entry["total_kg"], float64(0))
		historyRows = append(historyRows, []any{entry["date"], entry["squat_kg"], entry["bench_kg"], entry["deadlift_kg"], total, weight, dots(total, weight, sex), entry["context"]})
	}

	competitionRows := [][]any{}
	fedNames := map[string]any{}
	for _, fed := range maps(export.Federations["federations"]) {
		fedNames[values.Str2(fed["id"])] = first(fed["abbreviation"], fed["name"])
	}
	competitions := maps(program["competitions"])
	sort.SliceStable(competitions, func(i, j int) bool {
		return values.Str2(competitions[i]["date"]) < values.Str2(competitions[j]["date"])
	})
	for _, entry := range competitions {
		targets, _ := entry["targets"].(map[string]any)
		results, _ := entry["results"].(map[string]any)
		weight, source := entry["body_weight_kg"], "competition"
		if !values.Truthy(weight) {
			weight, source = markdown.ResolveBodyweightForDate(entry["date"], sessions, export.WeightLog, meta)
		}
		targetTotal, resultTotal := liftTotal(targets), liftTotal(results)
		var resultDots any
		if entry["status"] == "completed" {
			resultDots = dots(resultTotal, weight, sex)
		}
		ids, _ := entry["counts_toward_federation_ids"].([]any)
		names := []string{}
		for _, id := range ids {
			names = append(names, values.Str2(first(fedNames[values.Str2(id)], id)))
		}
		competitionRows = append(competitionRows, []any{entry["name"], entry["date"], entry["status"], first(fedNames[values.Str2(entry["federation_id"])], entry["federation"]), strings.Join(names, ", "), entry["location"], entry["hotel_required"], entry["weight_class_kg"], weight, source, targets["squat_kg"], targets["bench_kg"], targets["deadlift_kg"], targetTotal, dots(targetTotal, weight, sex), results["squat_kg"], results["bench_kg"], results["deadlift_kg"], resultTotal, resultDots, entry["place"], entry["decision_date"], entry["projection_snapshot_date"], entry["notes"], serialized(entry["post_meet_report"], map[string]any{}), serialized(entry["between_comp_plan"], map[string]any{}), serialized(entry["comp_day_protocol"], map[string]any{})})
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
	if len(weekly) > 0 {
		weeklyRows = weeklyAnalysisRows(weekly)
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
		liftRows = append(liftRows, []any{name, lift["progression_rate_kg_per_week"], first(lift["fit_quality"], lift["r_squared"], lift["r2"]), lift["kendall_tau"], lift["volume_change_pct"], lift["intensity_change_pct"], lift["failed_sets"], lift["rpe_trend"]})
	}
	if len(liftRows) == 0 {
		liftRows = append(liftRows, []any{"No tracked lifts in the window."})
	}
	liftRows = append(liftRows, nil, []any{"Projections"}, []any{"Comp", "Weeks Out", "Projected Total (kg)", "Confidence", "Method"})
	projections := maps(weekly["projections"])
	for _, projection := range projections {
		liftRows = append(liftRows, []any{first(projection["comp_name"], "(unscheduled)"), projection["weeks_to_comp"], projection["total"], projection["confidence"], projection["method"]})
	}
	if len(projections) == 0 {
		liftRows = append(liftRows, []any{first(weekly["projection_reason"], "No upcoming competitions to project.")})
	}
	missing := "Not yet generated — open the Analysis page and let the report render before exporting."
	if len(historyRows) == 0 {
		historyRows = append(historyRows, []any{"—", nil, nil, nil, nil, nil, nil, "No max history recorded"})
	}
	if len(weightRows) == 0 {
		weightRows = append(weightRows, []any{"—", nil, nil, "No weight log recorded"})
	}
	if len(profileRows) == 0 {
		profileRows = append(profileRows, []any{"—", "No lift profiles recorded on this program."})
	}
	if len(glossaryRows) == 0 {
		glossaryRows = append(glossaryRows, []any{"—", nil, nil, nil, nil, nil, nil, nil, "No glossary entries recorded"})
	}
	if len(competitionRows) == 0 {
		row := make([]any, 24)
		row[0], row[23] = "—", "No competitions recorded"
		competitionRows = append(competitionRows, row)
	}
	if len(weeklyRows) == 0 {
		weeklyRows = append(weeklyRows, []any{"Status", missing})
	}
	return []report.Table{
		goalTable(meta, maps(program["goals"]), maps(program["competitions"]), sex, export.Federations),
		federationTable(export.Federations),
		{Title: "Max History", Headers: []string{"Date", "Squat", "Bench", "Deadlift", "Total", "Bodyweight", "DOTS", "Context"}, Rows: historyRows},
		{Title: "Competitions", Headers: []string{"Name", "Date", "Status", "Federation", "Counts Toward", "Location", "Hotel Required", "Weight Class", "Body Weight", "Body Weight Source", "Target Squat", "Target Bench", "Target Deadlift", "Target Total", "Target DOTS", "Result Squat", "Result Bench", "Result Deadlift", "Result Total", "Result DOTS", "Place", "Decision Date", "Projection Snapshot Date", "Notes", "Post-Meet Report", "Between Comp Plan", "Comp Day Protocol"}, Rows: competitionRows},
		{Title: "Weight Log", Headers: []string{"Date", "Kg", "Delta From Previous", "Notes"}, Rows: weightRows},
		{Title: "Lift Profiles", Headers: []string{"Lift", "Technique", "Notes", "Volume Tolerance", "Stimulus Coefficient", "Coefficient Reasoning", "Confidence", "Updated At"}, Rows: profileRows},
		{Title: "Exercise Glossary", Headers: []string{"ID", "Name", "Category", "Fatigue Category", "Primary Muscles", "Secondary Muscles", "Tertiary Muscles", "Equipment", "Description", "How To Perform", "Why Do It", "Video URL", "Fatigue Axial", "Fatigue Neural", "Fatigue Peripheral", "Fatigue Systemic", "Fatigue Source", "Fatigue Reasoning", "E1RM Value", "E1RM Method", "E1RM Basis", "E1RM Confidence", "E1RM Updated At", "Archived"}, Rows: glossaryRows},
		{Title: "Weekly Analysis", Headers: []string{"Field", "Value"}, Rows: weeklyRows},
		{Title: "Per-Lift Metrics", Headers: []string{"Lift", "Progression (kg/wk)", "Fit Quality", "Kendall τ", "Volume Change %", "Intensity Change %", "Failed Sets", "RPE Trend"}, Rows: liftRows},
		correlationTable(export.Correlation, missing),
		evaluationTable(export.Evaluation, missing),
	}
}
