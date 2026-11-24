package workbook

import (
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
	"strings"
)

func nested(value map[string]any, key string) map[string]any {
	result, _ := value[key].(map[string]any)
	return result
}

func weeklyAnalysisRows(weekly map[string]any) [][]any {
	compliance := nested(weekly, "compliance")
	maxes := nested(weekly, "current_maxes")
	deload := nested(weekly, "deload_info")
	readiness := nested(weekly, "readiness_score")
	components := nested(readiness, "components")
	rows := [][]any{
		{"Current Week", weekly["week"]}, {"Block", weekly["block"]}, {"Sessions Analyzed", weekly["sessions_analyzed"]},
		{"Compliance — Planned", compliance["planned"]}, {"Compliance — Completed", compliance["completed"]}, {"Compliance — %", compliance["pct"]},
		{"Fatigue Index", weekly["fatigue_index"]}, {"Estimated DOTS", weekly["estimated_dots"]},
		{"Current Max — Squat (kg)", maxes["squat"]}, {"Current Max — Bench (kg)", maxes["bench"]}, {"Current Max — Deadlift (kg)", maxes["deadlift"]}, {"Current Maxes Method", maxes["method"]},
		{"Deload Weeks", deload["deload_weeks"]}, {"Break Weeks", deload["break_weeks"]}, {"Effective Training Weeks", deload["effective_training_weeks"]},
		{"Readiness Score", readiness["score"]}, {"Readiness Zone", readiness["zone"]}, {"Readiness - Fatigue", components["fatigue_norm"]},
		{"Readiness - RPE Drift", components["rpe_drift"]}, {"Readiness - Wellness", components["wellness"]}, {"Readiness - Trend", components["performance_trend"]}, {"Readiness - BW Deviation", components["bw_deviation"]},
	}
	for _, field := range [][2]string{{"Exercise Stats", "exercise_stats"}, {"Fatigue Components", "fatigue_components"}, {"Fatigue Dimensions", "fatigue_dimensions"}, {"Banister", "banister"}, {"Monotony / Strain", "monotony_strain"}, {"Decoupling", "decoupling"}, {"Taper Quality", "taper_quality"}, {"Specificity Ratio", "specificity_ratio"}, {"INOL", "inol"}, {"ACWR", "acwr"}, {"Volume Landmarks", "volume_landmarks"}, {"Peaking Timeline", "peaking_timeline"}, {"Projection Calibration", "projection_calibration"}, {"Bodyweight Trend", "bodyweight_trend"}} {
		rows = append(rows, []any{field[0], serialized(weekly[field[1]], map[string]any{})})
	}
	return append(rows, []any{"Alerts", serialized(weekly["alerts"], []any{})}, []any{"Flags", weekly["flags"]})
}

func reportHeader(data map[string]any, fields [][2]string) [][]any {
	rows := make([][]any, 0, len(fields)+1)
	for _, field := range fields {
		rows = append(rows, []any{field[0], data[field[1]]})
	}
	return append(rows, nil)
}

func correlationTable(data map[string]any, missing string) report.Table {
	if len(data) == 0 {
		return report.Table{Title: "ROI Correlation", Headers: []string{"Field", "Value"}, Rows: [][]any{{"Status", missing}}}
	}
	rows := reportHeader(data, [][2]string{{"Summary", "summary"}, {"Generated At", "generated_at"}, {"Window Start", "window_start"}, {"Weeks", "weeks"}, {"Cached", "cached"}})
	if values.Truthy(data["insufficient_data"]) {
		rows = append(rows, []any{"Insufficient data", data["insufficient_data_reason"]})
	} else {
		rows = append(rows, []any{"Findings"}, []any{"Exercise", "Lift", "Direction", "Strength", "Reasoning", "Caveat"})
		findings := maps(data["findings"])
		for _, f := range findings {
			rows = append(rows, []any{first(f["driver"], f["exercise"]), f["lift"], first(f["effect"], f["correlation_direction"]), first(f["confidence"], f["strength"]), joinValues(f["evidence"], f["mechanism"], f["reasoning"]), joinValues(f["action"], f["caveat"])})
		}
		if len(findings) == 0 {
			rows = append(rows, []any{"No findings reported."})
		}
	}
	return report.Table{Title: "ROI Correlation", Rows: rows}
}

func joinValues(items ...any) string {
	parts := []string{}
	for _, item := range items {
		if values.Truthy(item) {
			parts = append(parts, values.Str2(item))
		}
	}
	return strings.Join(parts, " ")
}

func evaluationTable(data map[string]any, missing string) report.Table {
	if len(data) == 0 {
		return report.Table{Title: "Program Evaluation", Headers: []string{"Field", "Value"}, Rows: [][]any{{"Status", missing}}}
	}
	rows := reportHeader(data, [][2]string{{"Stance", "stance"}, {"Summary", "summary"}, {"Conclusion", "conclusion"}, {"Generated At", "generated_at"}, {"Window Start", "window_start"}, {"Weeks", "weeks"}, {"Cached", "cached"}})
	if values.Truthy(data["insufficient_data"]) {
		return report.Table{Title: "Program Evaluation", Rows: append(rows, []any{"Insufficient data", data["insufficient_data_reason"]})}
	}
	for _, field := range [][2]string{{"What's Working", "what_is_working"}, {"What's Not Working", "what_is_not_working"}, {"Monitoring Focus", "monitoring_focus"}} {
		rows = append(rows, []any{field[0]})
		items, _ := data[field[1]].([]any)
		for _, item := range items {
			rows = append(rows, []any{item})
		}
		if len(items) == 0 {
			rows = append(rows, []any{"(none)"})
		}
		rows = append(rows, nil)
	}
	addSection := func(title, key string, headers, fields []string, source map[string]any) {
		rows = append(rows, []any{title})
		h := make([]any, len(headers))
		for i, v := range headers {
			h[i] = v
		}
		rows = append(rows, h)
		items := maps(source[key])
		for _, item := range items {
			row := make([]any, len(fields))
			for i, field := range fields {
				row[i] = item[field]
			}
			rows = append(rows, row)
		}
		if len(items) == 0 {
			rows = append(rows, []any{"(none)"})
		}
		rows = append(rows, nil)
	}
	addSection("Competition Alignment", "competition_alignment", []string{"Competition", "Role", "Alignment", "Reason"}, []string{"competition", "role", "alignment", "reason"}, data)
	addSection("Goal Status", "goal_status", []string{"Goal", "Priority", "Status", "Reason"}, []string{"goal", "priority", "status", "reason"}, data)
	addSection("Competition Strategy", "competition_strategy", []string{"Competition", "Priority", "Approach", "Reason"}, []string{"competition", "priority", "approach", "reason"}, data)
	weight := nested(data, "weight_class_strategy")
	rows = append(rows, []any{"Weight Class Strategy"}, []any{"Recommendation", weight["recommendation"]}, []any{"Recommended Weight Class", weight["recommended_weight_class_kg"]})
	h := []any{"Option Weight Class", "Suitability", "Reason"}
	rows = append(rows, h)
	options := maps(weight["viable_options"])
	for _, option := range options {
		rows = append(rows, []any{option["weight_class_kg"], option["suitability"], option["reason"]})
	}
	if len(options) == 0 {
		rows = append(rows, []any{"(none)"})
	}
	rows = append(rows, nil)
	addSection("Small Changes", "small_changes", []string{"Change", "Why", "Risk", "Priority"}, []string{"change", "why", "risk", "priority"}, data)
	return report.Table{Title: "Program Evaluation", Rows: rows}
}
