package report

import (
	"math"
	"sort"
	"strings"
	"unicode"
)

type column struct{ label, path string }

func object(value any) map[string]any {
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return map[string]any{}
}

func records(value any) []map[string]any {
	raw, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if row, ok := item.(map[string]any); ok {
			result = append(result, row)
		}
	}
	return result
}

func fields(row map[string]any, keys ...string) []any {
	out := make([]any, 0, len(keys))
	for _, key := range keys {
		var value any = row
		for _, part := range strings.Split(strings.TrimSuffix(key, "%"), ".") {
			value = object(value)[part]
		}
		if n, ok := number(value); ok {
			if strings.HasSuffix(key, "%") {
				value = math.RoundToEven(n*1000) / 10
			} else {
				value = math.RoundToEven(n*100) / 100
			}
		}
		out = append(out, value)
	}
	return out
}

func measures(row map[string]any, columns []column) [][]any {
	result := [][]any{}
	for _, c := range columns {
		value := fields(row, c.path)[0]
		if value != nil {
			result = append(result, []any{c.label, value})
		}
	}
	return result
}

func sortedKeys(row map[string]any) []string {
	keys := make([]string, 0, len(row))
	for key := range row {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func WeeklyTables(weekly map[string]any) []Table {
	tables := []Table{}
	add := func(title string, headers []string, rows [][]any) {
		if len(rows) > 0 {
			tables = append(tables, Table{title, headers, rows})
		}
	}
	summary := func(title string, value any, columns []column) {
		add(title, []string{"Metric", "Value"}, measures(object(value), columns))
	}
	summary("Compliance", weekly["compliance"], []column{
		{"Phase", "phase"}, {"Planned sessions", "planned"}, {"Completed sessions", "completed"}, {"Missed sessions", "missed"},
		{"Session completion (%)", "pct"}, {"Planned sets", "planned_sets"}, {"Completed sets", "completed_sets"}, {"Set completion (%)", "set_pct"},
		{"Planned reps", "planned_reps"}, {"Completed reps", "completed_reps"}, {"Rep completion (%)", "rep_pct"},
		{"Planned volume (kg)", "planned_volume"}, {"Completed volume (kg)", "completed_volume"}, {"Volume completion (%)", "vol_pct"},
	})
	fatigue := object(weekly["fatigue_components"])
	fatigueCopy := map[string]any{}
	for k, v := range fatigue {
		fatigueCopy[k] = v
	}
	fatigueCopy["index"] = weekly["fatigue_index"]
	summary("Fatigue Index", fatigueCopy, []column{
		{"Fatigue index (%)", "index%"}, {"Window mean (%)", "window_mean_fi%"}, {"Window peak (%)", "window_peak_fi%"},
		{"Failure stress (%)", "failure_stress%"}, {"Acute spike stress (%)", "acute_spike_stress%"}, {"RPE stress (%)", "rpe_stress%"},
		{"Reservoir stress (%)", "chronic_load_stress%"}, {"Overload streak (%)", "overload_streak%"}, {"Intensity density stress (%)", "intensity_density_stress%"},
		{"Monotony stress (%)", "monotony_stress%"}, {"Context weeks", "fatigue_context_weeks_used"}, {"Context confidence", "fatigue_context_confidence"},
	})
	summary("Readiness", weekly["readiness_score"], []column{
		{"Overall score", "score"}, {"Zone", "zone"}, {"Training score", "training_score"}, {"External score", "external_score"},
		{"Fatigue (%)", "components.fatigue_norm%"}, {"RPE drift (%)", "components.rpe_drift%"}, {"Wellness (%)", "components.wellness%"},
		{"Performance trend (%)", "components.performance_trend%"}, {"Bodyweight deviation (%)", "components.bw_deviation%"},
		{"Overall confidence (%)", "readiness_confidence%"}, {"Training confidence (%)", "training_readiness_confidence%"}, {"External confidence (%)", "external_readiness_confidence%"},
	})
	summary("Specificity", weekly["specificity_ratio"], []column{
		{"Narrow (%)", "narrow%"}, {"Broad (%)", "broad%"}, {"Competition sets", "sbd_sets"}, {"Accessory sets", "secondary_sets"},
		{"Weighted sets", "weighted_sets"}, {"Total sets", "total_sets"}, {"Narrow expected min (%)", "expected_band.narrow.min%"},
		{"Narrow expected max (%)", "expected_band.narrow.max%"}, {"Broad expected min (%)", "expected_band.broad.min%"},
		{"Broad expected max (%)", "expected_band.broad.max%"}, {"Narrow status", "narrow_status"}, {"Broad status", "broad_status"},
	})
	summary("Taper Quality", weekly["taper_quality"], []column{
		{"Score", "score"}, {"Label", "label"}, {"Weeks to meet", "weeks_to_comp"}, {"Volume reduction (%)", "components.volume_reduction%"},
		{"Intensity maintained (%)", "components.intensity_maintained%"}, {"Fatigue trend (%)", "components.fatigue_trend%"},
		{"TSB (%)", "components.tsb%"}, {"Data status", "reason"},
	})
	summary("Projection Calibration", weekly["projection_calibration"], []column{
		{"Calibrated", "calibrated"}, {"Meets", "meets"}, {"Median performance realization ratio", "median_prr"}, {"Projection multiplier", "lambda_multiplier"},
	})
	series := func(title string, headers []string, values any, keys ...string) {
		rows := [][]any{}
		for _, row := range records(values) {
			rows = append(rows, fields(row, keys...))
		}
		add(title, headers, rows)
	}
	series("Foster Monotony and Strain", []string{"Week", "Monotony", "Raw monotony", "Strain", "Strain index", "Nonzero training days"}, object(weekly["monotony_strain"])["weekly"], "week_start", "monotony", "monotony_raw", "strain", "strain_index", "nonzero_training_days")
	series("Peaking Timeline", []string{"Date", "Actual TSB", "Projected TSB"}, object(weekly["peaking_timeline"])["series"], "date", "actual_tsb", "projected_tsb")
	series("Fatigue Decoupling", []string{"Week", "e1RM slope (%/week)", "Fatigue slope (pp/week)", "Decoupling"}, object(weekly["decoupling"])["series"], "week_start", "e1rm_slope_pct_per_week", "fi_slope_pct_points_per_week", "decoupling")
	series("Meet Projections", []string{"Meet", "Weeks to meet", "Squat (kg)", "Bench (kg)", "Deadlift (kg)", "Total (kg)", "Confidence (%)", "Method"}, weekly["projections"], "comp_name", "weeks_to_comp", "lifts.squat.projected", "lifts.bench.projected", "lifts.deadlift.projected", "total", "confidence%", "method")
	lifts := object(weekly["lifts"])
	allLifts := map[string]any{}
	for key, value := range lifts {
		allLifts[key] = value
	}
	for key, value := range object(weekly["per_lift"]) {
		allLifts[key] = value
	}
	liftRows := [][]any{}
	for _, lift := range sortedKeys(allLifts) {
		row := append([]any{title(lift)}, fields(object(object(weekly["per_lift"])[lift]), "sets", "raw_sets", "volume", "raw_volume", "frequency", "exposure_frequency")...)
		row = append(row, fields(object(lifts[lift]), "progression_rate_kg_per_week", "kendall_tau", "fit_quality%", "volume_change_pct", "intensity_change_pct", "failed_sets", "rpe_trend")...)
		liftRows = append(liftRows, row)
	}
	add("Per-Lift Breakdown", []string{"Lift", "Sets", "Raw sets", "Volume (kg)", "Raw volume (kg)", "Frequency", "Exposure frequency", "Progression (kg/week)", "Kendall tau", "Fit quality (%)", "Volume change (%)", "Intensity change (%)", "Failed sets", "RPE trend"}, liftRows)
	breakdowns := object(weekly["per_lift"])
	accessories := [][]any{}
	for _, lift := range sortedKeys(breakdowns) {
		for _, accessory := range records(object(breakdowns[lift])["accessories"]) {
			accessories = append(accessories, append([]any{title(lift)}, fields(accessory, "name", "transfer", "sets", "weighted_sets", "volume")...))
		}
	}
	add("Accessory Workload", []string{"Lift", "Exercise", "Transfer", "Sets", "Weighted sets", "Volume (kg)"}, accessories)
	exerciseRows := [][]any{}
	exercises := object(weekly["exercise_stats"])
	for _, name := range sortedKeys(exercises) {
		exerciseRows = append(exerciseRows, append([]any{name}, fields(object(exercises[name]), "total_sets", "total_volume", "max_kg")...))
	}
	add("Exercise Volume", []string{"Exercise", "Total sets", "Volume (kg)", "Max (kg)"}, exerciseRows)
	muscles := object(object(weekly["muscle_volume"])["muscles"])
	muscleRows := [][]any{}
	for _, name := range sortedKeys(muscles) {
		muscleRows = append(muscleRows, append([]any{title(strings.ReplaceAll(name, "_", " "))}, fields(object(muscles[name]), "weekly_sets", "total_sets", "status", "landmarks.mv", "landmarks.mev", "landmarks.mav_low", "landmarks.mav_high", "landmarks.mrv")...))
	}
	add("Muscle Volume", []string{"Muscle", "Sets/week", "Total sets", "Status", "MV", "MEV", "MAV low", "MAV high", "MRV"}, muscleRows)
	acwr := object(weekly["acwr"])
	summary("EWMA ACWR Summary", acwr, []column{{"Composite", "composite"}, {"Zone", "composite_label"}, {"Status", "reason"}})
	dimensions := object(acwr["dimensions"])
	acwrRows := [][]any{}
	for _, name := range sortedKeys(dimensions) {
		row := append([]any{title(name)}, fields(object(dimensions[name]), "value", "acute", "chronic", "label")...)
		row = append(row, fields(object(acwr["weights_used"]), name+"%")...)
		acwrRows = append(acwrRows, row)
	}
	add("EWMA ACWR", []string{"Dimension", "Ratio", "Acute", "Chronic", "Zone", "Weight (%)"}, acwrRows)
	fatigueDimensions := object(weekly["fatigue_dimensions"])
	dimensionRows := [][]any{}
	for _, group := range []struct{ key, label string }{{"weekly", "Raw"}, {"normalized", "Normalized"}} {
		values := object(fatigueDimensions[group.key])
		for _, week := range sortedKeys(values) {
			dimensionRows = append(dimensionRows, append([]any{week, group.label}, fields(object(values[week]), "axial", "neural", "peripheral", "systemic")...))
		}
	}
	add("Fatigue Dimensions", []string{"Week", "Series", "Axial", "Neural", "Peripheral", "Systemic"}, dimensionRows)
	inol := object(weekly["inol"])
	inolLifts := object(inol["lifts"])
	inolRows := [][]any{}
	for _, lift := range sortedKeys(inolLifts) {
		row := append([]any{title(lift)}, fields(object(inolLifts[lift]), "adjusted", "raw", "coefficient", "coefficient_source")...)
		row = append(row, fields(object(object(inol["phase_adjusted_thresholds"])[lift]), "display_low", "display_high", "phase_multiplier")...)
		row = append(row, fields(object(object(inol["trend_pressure"])[lift]), "value%")...)
		inolRows = append(inolRows, row)
	}
	add("Stimulus-Adjusted INOL", []string{"Lift", "Adjusted", "Raw", "Coefficient", "Coefficient source", "Target low", "Target high", "Phase multiplier", "Trend pressure (%)"}, inolRows)
	weeklyInol := object(inol["per_lift_per_week"])
	weeklyInolRows := [][]any{}
	for _, lift := range sortedKeys(weeklyInol) {
		weeks := object(weeklyInol[lift])
		raw := object(object(inol["raw_per_lift_per_week"])[lift])
		for _, week := range sortedKeys(weeks) {
			weeklyInolRows = append(weeklyInolRows, []any{title(lift), week, weeks[week], raw[week]})
		}
	}
	add("Weekly INOL", []string{"Lift", "Week", "Adjusted", "Raw"}, weeklyInolRows)
	intensity := object(weekly["ri_distribution"])
	perLift := object(intensity["per_lift"])
	distribution := map[string]any{"overall": intensity["overall"]}
	for k, v := range perLift {
		distribution[k] = v
	}
	intensityRows := [][]any{}
	for _, lift := range sortedKeys(distribution) {
		bands := object(distribution[lift])
		for _, band := range sortedKeys(bands) {
			intensityRows = append(intensityRows, append([]any{title(lift), title(band)}, fields(object(bands[band]), "count", "pct")...))
		}
	}
	add("Relative Intensity", []string{"Lift", "Zone", "Sets", "Percent"}, intensityRows)
	landmarks := object(weekly["volume_landmarks"])
	landmarkRows := [][]any{}
	for _, lift := range sortedKeys(landmarks) {
		landmarkRows = append(landmarkRows, append([]any{title(lift)}, fields(object(landmarks[lift]), "mv", "mev", "mav", "mrv", "confidence", "reason")...))
	}
	add("Volume Landmarks", []string{"Lift", "MV", "MEV", "MAV", "MRV", "Confidence", "Data status"}, landmarkRows)
	banister := object(weekly["banister"])
	summary("Banister Summary", banister, []column{{"Fitness (CTL)", "ctl_today"}, {"Fatigue (ATL)", "atl_today"}, {"Form (TSB)", "tsb_today"}, {"Data status", "reason"}})
	start, _ := weekly["window_start"].(string)
	end, _ := weekly["window_end"].(string)
	banisterRows := [][]any{}
	for _, row := range records(banister["series"]) {
		date, _ := row["date"].(string)
		if (start == "" || date >= start) && (end == "" || date <= end) {
			banisterRows = append(banisterRows, fields(row, "date", "ctl", "atl", "tsb", "load"))
		}
	}
	add("Banister Fitness and Fatigue", []string{"Date", "Fitness (CTL)", "Fatigue (ATL)", "Form (TSB)", "Load"}, banisterRows)
	timeline := object(weekly["peaking_timeline"])
	summary("Peaking Status", timeline, []column{{"Status", "status_label"}, {"Details", "status_message"}, {"Meet date", "comp_date"}, {"Current form (TSB)", "current_tsb"}, {"Peak date", "peak_date"}, {"Peak distance (days)", "peak_delta_days"}, {"Closest peak", "closest_peak_date"}, {"Closest projected TSB", "closest_projected_tsb"}})
	series("Peaking Specificity", []string{"Date", "Narrow (%)", "Broad (%)", "Weeks to meet", "Narrow min (%)", "Narrow max (%)", "Broad min (%)", "Broad max (%)"}, timeline["specificity_points"], "date", "narrow%", "broad%", "weeks_to_comp", "expected_band.narrow.min%", "expected_band.narrow.max%", "expected_band.broad.min%", "expected_band.broad.max%")
	summary("Fatigue Decoupling Summary", weekly["decoupling"], []column{{"Current decoupling", "current.decoupling"}, {"Data status", "reason"}})
	alerts := [][]any{}
	if raw, ok := weekly["alerts"].([]any); ok {
		for _, alert := range raw {
			if row, ok := alert.(map[string]any); ok {
				alerts = append(alerts, fields(row, "severity", "source", "message", "raw_detail"))
			} else {
				alerts = append(alerts, []any{nil, nil, alert, nil})
			}
		}
	}
	add("Analysis Alerts", []string{"Severity", "Source", "Message", "Detail"}, alerts)
	flags := [][]any{}
	if raw, ok := weekly["flags"].([]any); ok {
		for _, flag := range raw {
			flags = append(flags, []any{flag})
		}
	}
	add("Analysis Flags", []string{"Flag"}, flags)
	order := []string{"Compliance", "Fatigue Index", "Readiness", "Per-Lift Breakdown", "Accessory Workload", "Exercise Volume", "Muscle Volume", "Foster Monotony and Strain", "EWMA ACWR Summary", "EWMA ACWR", "Fatigue Dimensions", "Stimulus-Adjusted INOL", "Weekly INOL", "Relative Intensity", "Specificity", "Volume Landmarks", "Banister Summary", "Banister Fitness and Fatigue", "Peaking Status", "Peaking Timeline", "Peaking Specificity", "Fatigue Decoupling Summary", "Fatigue Decoupling", "Taper Quality", "Meet Projections", "Projection Calibration", "Analysis Alerts", "Analysis Flags"}
	rank := make(map[string]int, len(order))
	for i, name := range order {
		rank[name] = i
	}
	sort.SliceStable(tables, func(i, j int) bool { return rank[tables[i].Title] < rank[tables[j].Title] })
	return tables
}

func title(value string) string {
	words := strings.Fields(value)
	for i, word := range words {
		chars := []rune(strings.ToLower(word))
		if len(chars) > 0 {
			chars[0] = unicode.ToUpper(chars[0])
		}
		words[i] = string(chars)
	}
	return strings.Join(words, " ")
}

func AnalysisTables(weekly map[string]any, notes []map[string]any, meta map[string]any) []Table {
	tables := append(WeeklyTables(weekly), NutritionTables(notes, meta)...)
	measurements := measures(meta, []column{{"Height (cm)", "height_cm"}, {"Arm wingspan (cm)", "arm_wingspan_cm"}, {"Leg length (cm)", "leg_length_cm"}})
	if len(measurements) > 0 {
		tables = append(tables, Table{"Athlete Measurements", []string{"Measurement", "Value"}, measurements})
	}
	return tables
}
