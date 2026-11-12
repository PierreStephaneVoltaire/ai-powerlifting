package render

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	MarkdownType = "text/markdown; charset=utf-8"
	XLSXType     = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

	minEvaluationWeeks = 4
	insufficientReason = "At least 4 completed weeks are required for a useful block program evaluation."
	timestampLayout    = "2006-01-02T15:04:05.000Z"
)

var (
	lifts       = []string{"squat", "bench", "deadlift", "total"}
	nonSlug     = regexp.MustCompile(`[^a-z0-9]+`)
	slugTrimmed = regexp.MustCompile(`^-+|-+$`)
)

type block struct {
	bundle     map[string]any
	meta       map[string]any
	historical map[string]any
	weekly     map[string]any
	evaluation map[string]any
	correlated map[string]any
}

func newBlock(bundle map[string]any) block {
	b := block{
		bundle:     bundle,
		meta:       record(bundle["block"]),
		historical: record(bundle["historical"]),
		weekly:     record(bundle["weekly"]),
	}
	if reports, ok := bundle["programEvaluation"].(map[string]any); ok {
		b.evaluation = reports
	}
	if reports, ok := bundle["correlation"].(map[string]any); ok {
		b.correlated = reports
	}
	if weeks, _ := number(b.meta["weekCount"]); weeks < minEvaluationWeeks {
		if b.evaluation == nil {
			b.evaluation = map[string]any{"insufficient_data_reason": insufficientReason}
		}
		if b.correlated == nil {
			b.correlated = map[string]any{}
		}
	}
	return b
}

func (b block) IsCurrent() bool {
	current, _ := b.meta["isCurrent"].(bool)
	return current
}

func BlockIsCurrent(bundle map[string]any) bool {
	return newBlock(bundle).IsCurrent()
}

func BlockFilename(bundle map[string]any, format string) string {
	meta := record(newBlock(bundle).meta)
	label := firstText(meta["label"], meta["block"], meta["blockKey"])
	slug := strings.ToLower(label)
	slug = nonSlug.ReplaceAllString(slug, "-")
	slug = slugTrimmed.ReplaceAllString(slug, "")
	slug = truncate(slug, 80)
	if slug == "" {
		slug = text(meta["blockKey"])
	}
	extension := "md"
	if format == "xlsx" {
		extension = "xlsx"
	}
	return fmt.Sprintf("block-analysis-%s.%s", slug, extension)
}

func firstText(values ...any) string {
	for _, value := range values {
		if candidate := text(value); candidate != "" {
			return candidate
		}
	}
	return ""
}

func BlockMarkdown(bundle map[string]any, now time.Time) string {
	b := newBlock(bundle)
	lines := []string{
		"# " + text(b.meta["label"]) + " Block Analysis",
		"",
		"Generated: " + now.UTC().Format(timestampLayout),
		"Cached analysis generated: " + text(bundle["generatedAt"]),
	}
	for _, table := range b.tables() {
		lines = append(lines, "", "## "+table.Title)
		lines = append(lines, markdownTable(table.Rows)...)
	}
	return strings.Join(lines, "\n") + "\n"
}

func BlockWorkbook(bundle map[string]any) ([]byte, error) {
	return workbook(newBlock(bundle).tables())
}

func (b block) tables() []Table {
	fixedTables := []Table{
		{"Summary", "Summary", b.summaryRows()},
		{"Block Start Maxes", "Start Maxes", b.startMaxRows()},
		{"Strength Start / End", "Strength", b.strengthRows()},
		{"Competition Outcome", "Competition", competitionRows(b.historical["competitionOutcome"])},
		{"Data Quality", "Data Quality", dataQualityRows(list(b.historical["missingData"]))},
		{"Weekly Analysis", "Weekly Analysis", b.weeklySummaryRows()},
		{"Lift Metrics", "Lift Metrics", b.liftMetricRows()},
	}
	optional := []Table{
		{"Stimulus-Adjusted INOL", "INOL", b.inolRows()},
		{"EWMA ACWR", "ACWR", b.acwrRows()},
		{"Relative Intensity Distribution", "RI Distribution", b.riRows()},
		{"Specificity Ratio", "Specificity", b.specificityRows()},
		{"Fatigue Dimensions", "Fatigue Dimensions", b.fatigueDimensionRows()},
		{"Projections", "Projections", b.projectionRows()},
		{"Alerts", "Alerts", b.alertRows()},
		{"Exercise Stats", "Exercise Stats", b.exerciseStatsRows()},
		{"Program Analysis", "Program Analysis", evaluationRows(b.evaluation)},
		{"Exercise ROI Correlation", "ROI Correlation", correlationRows(b.correlated)},
	}
	for _, table := range optional {
		if len(table.Rows) > 0 {
			fixedTables = append(fixedTables, table)
		}
	}
	return fixedTables
}

func (b block) summaryRows() []Row {
	summary := record(b.historical["analyticsSummary"])
	training := "No"
	if trainingOnly, _ := b.meta["trainingOnly"].(bool); trainingOnly {
		training = "Yes"
	}
	return []Row{
		{"Metric", "Value"},
		{"Block", b.meta["label"]},
		{"Date range", compact(b.meta["startDate"]) + " to " + compact(b.meta["endDate"])},
		{"Weeks", b.meta["weekCount"]},
		{"Week range", "W" + compact(b.meta["weekStart"]) + "-W" + compact(b.meta["weekEnd"])},
		{"Sessions", compact(b.meta["completedSessions"]) + "/" + compact(b.meta["totalSessions"]) + " completed"},
		{"Completed sessions analyzed", summary["sessionsAnalyzed"]},
		{"Compliance", formatRawPct(summary["compliancePct"])},
		{"Total completed volume", formatKg(summary["totalVolumeKg"])},
		{"Fatigue index", formatPct(summary["fatigueIndex"])},
		{"ACWR composite", formatNumber(summary["acwrComposite"], 2)},
		{"Training only", training},
		{"Generated", b.bundle["generatedAt"]},
	}
}

func (b block) startMaxRows() []Row {
	manual, hasManual := b.historical["manualStartMaxes"].(map[string]any)
	strength := record(b.historical["startStrength"])
	source := b.historical["startMaxesSource"]
	rows := []Row{{"Lift", "Start max", "Source"}}
	for _, lift := range lifts {
		value := manual[lift+"_kg"]
		if value == nil {
			value = strength[lift]
		}
		rows = append(rows, Row{titleize(lift), formatKg(value), source})
	}
	label := ""
	if hasManual {
		label = "Manual entry"
	}
	return append(rows, Row{"Updated", manual["updated_at"], label})
}

func (b block) strengthRows() []Row {
	rows := []Row{{"Lift", "Start", "End", "Delta"}}
	for _, lift := range lifts {
		rows = append(rows, Row{
			titleize(lift),
			formatKg(record(b.historical["startStrength"])[lift]),
			formatKg(record(b.historical["endStrength"])[lift]),
			formatKg(record(b.historical["strengthDelta"])[lift]),
		})
	}
	return rows
}

func competitionRows(value any) []Row {
	outcome, ok := value.(map[string]any)
	if !ok {
		return []Row{{"Metric", "Value"}, {"Competition", "No completed competition maps to this block."}}
	}
	posted := "No"
	if captured, _ := outcome["postMeetReportCaptured"].(bool); captured {
		posted = "Yes"
	}
	results, hasResults := outcome["results"].(map[string]any)
	rows := []Row{
		{"Metric", "Value"},
		{"Competition", outcome["competitionName"]},
		{"Date", outcome["competitionDate"]},
		{"Bodyweight", formatKg(outcome["bodyweightKg"])},
		{"Actual total", formatKg(results["total_kg"])},
		{"DOTS", formatNumber(outcome["dots"], 2)},
		{"IPF GL", formatNumber(outcome["ipfGl"], 2)},
		{"Post-meet report captured", posted},
	}
	if hasResults {
		rows = append(rows,
			Row{"Actual squat", formatKg(results["squat_kg"])},
			Row{"Actual bench", formatKg(results["bench_kg"])},
			Row{"Actual deadlift", formatKg(results["deadlift_kg"])},
		)
	}
	if accuracy, ok := outcome["projectionAccuracy"].(map[string]any); ok {
		rows = append(rows, Row{"Projection accuracy", "Actual / projected / delta"})
		for _, key := range sortedKeys(accuracy) {
			item := record(accuracy[key])
			rows = append(rows, Row{
				titleize(strings.Replace(key, "_kg", "", 1)),
				formatKg(item["actualKg"]) + " / " + formatKg(item["projectedKg"]) + " / " + formatKg(item["deltaKg"]),
			})
		}
	}
	return rows
}

func dataQualityRows(flags []any) []Row {
	if len(flags) == 0 {
		return []Row{{"Severity", "Code", "Label"}, {"complete", "", "Complete"}}
	}
	rows := []Row{{"Severity", "Code", "Label"}}
	for _, raw := range flags {
		flag := record(raw)
		rows = append(rows, Row{flag["severity"], flag["code"], flag["label"]})
	}
	return rows
}

func (b block) weeklySummaryRows() []Row {
	compliance := record(b.weekly["compliance"])
	maxes := record(b.weekly["current_maxes"])
	components := record(b.weekly["fatigue_components"])
	complianceText := "--"
	if pct, present := compliance["pct"]; present {
		complianceText = formatRawPct(pct)
	}
	return []Row{
		{"Metric", "Value"},
		{"Block", text(b.weekly["block"])},
		{"Selected weeks", compact(b.weekly["selected_week_start"]) + "-" + compact(b.weekly["selected_week_end"])},
		{"Window", compact(b.weekly["window_start"]) + " to " + compact(b.weekly["window_end"])},
		{"Sessions analyzed", numberOrBlank(b.weekly["sessions_analyzed"])},
		{"Compliance", complianceText},
		{"Current squat", formatKg(maxes["squat"])},
		{"Current bench", formatKg(maxes["bench"])},
		{"Current deadlift", formatKg(maxes["deadlift"])},
		{"Estimated DOTS", formatNumber(b.weekly["estimated_dots"], 2)},
		{"Fatigue index", formatPct(b.weekly["fatigue_index"])},
		{"Window mean fatigue", formatPct(components["window_mean_fi"])},
		{"Window peak fatigue", formatPct(components["window_peak_fi"])},
		{"Projection reason", text(b.weekly["projection_reason"])},
	}
}

func (b block) liftMetricRows() []Row {
	lifted := record(b.weekly["lifts"])
	rows := []Row{{"Lift", "Progression kg/wk", "Fit quality", "Volume change", "Intensity change", "Failed sets", "RPE trend"}}
	for _, lift := range liftOrder(lifted) {
		metrics := record(lifted[lift])
		rows = append(rows, Row{
			titleize(lift),
			formatNumber(metrics["progression_rate_kg_per_week"], 2),
			formatNumber(metrics["fit_quality"], 2),
			formatRawPct(metrics["volume_change_pct"]),
			formatRawPct(metrics["intensity_change_pct"]),
			numberOrBlank(metrics["failed_sets"]),
			text(metrics["rpe_trend"]),
		})
	}
	return rows
}

func (b block) inolRows() []Row {
	inol := record(b.weekly["inol"])
	average := record(inol["avg_inol"])
	if len(average) == 0 {
		return nil
	}
	raw, coefficients := record(inol["raw_avg_inol"]), record(inol["stimulus_coefficients"])
	rows := []Row{{"Lift", "Adjusted INOL", "Raw INOL", "Stimulus coefficient"}}
	for _, lift := range liftOrder(average) {
		rows = append(rows, Row{titleize(lift), formatNumber(average[lift], 2), formatNumber(raw[lift], 2), formatNumber(coefficients[lift], 2)})
	}
	return rows
}

func (b block) acwrRows() []Row {
	acwr := record(b.weekly["acwr"])
	if len(acwr) == 0 {
		return nil
	}
	if acwr["status"] == "insufficient_data" {
		return []Row{{"Metric", "Value"}, {"Status", "Insufficient data"}, {"Reason", text(acwr["reason"])}}
	}
	rows := []Row{
		{"Dimension", "Value", "Zone", "Label"},
		{"Composite", formatNumber(acwr["composite"], 2), text(acwr["composite_zone"]), text(acwr["composite_label"])},
	}
	dimensions := record(acwr["dimensions"])
	for _, key := range sortedKeys(dimensions) {
		info := record(dimensions[key])
		rows = append(rows, Row{titleize(key), formatNumber(info["value"], 2), text(info["zone"]), text(info["label"])})
	}
	return rows
}

func (b block) riRows() []Row {
	overall := record(record(b.weekly["ri_distribution"])["overall"])
	if len(overall) == 0 {
		return nil
	}
	rows := []Row{{"Bucket", "Count", "Percent"}}
	for _, bucket := range sortedKeys(overall) {
		item := record(overall[bucket])
		rows = append(rows, Row{titleize(bucket), numberOrBlank(item["count"]), formatRawPct(item["pct"])})
	}
	return rows
}

func (b block) specificityRows() []Row {
	specificity := record(b.weekly["specificity_ratio"])
	if len(specificity) == 0 {
		return nil
	}
	return []Row{
		{"Metric", "Value"},
		{"Narrow", formatPct(specificity["narrow"])},
		{"Broad", formatPct(specificity["broad"])},
		{"Total sets", numberOrBlank(specificity["total_sets"])},
		{"SBD sets", numberOrBlank(specificity["sbd_sets"])},
		{"Secondary sets", numberOrBlank(specificity["secondary_sets"])},
		{"Narrow status", text(specificity["narrow_status"])},
		{"Broad status", text(specificity["broad_status"])},
	}
}

func (b block) fatigueDimensionRows() []Row {
	weekly := record(record(b.weekly["fatigue_dimensions"])["weekly"])
	if len(weekly) == 0 {
		return nil
	}
	weeks := sortedKeys(weekly)
	sort.SliceStable(weeks, func(a, c int) bool { return weekNumber(weeks[a]) < weekNumber(weeks[c]) })
	rows := []Row{{"Week", "Axial", "Neural", "Peripheral", "Systemic"}}
	for _, week := range weeks {
		item := record(weekly[week])
		rows = append(rows, Row{"W" + week, formatNumber(item["axial"], 1), formatNumber(item["neural"], 1), formatNumber(item["peripheral"], 1), formatNumber(item["systemic"], 1)})
	}
	return rows
}

func weekNumber(key string) float64 {
	var value float64
	if _, err := fmt.Sscanf(key, "%g", &value); err != nil {
		return 0
	}
	return value
}

func (b block) projectionRows() []Row {
	rows := []Row{{"Competition", "Projected total", "Confidence", "Weeks to comp", "Method"}}
	for _, raw := range list(b.weekly["projections"]) {
		projection := record(raw)
		if len(projection) == 0 {
			continue
		}
		name := text(projection["comp_name"])
		if name == "" {
			name = "Projected total"
		}
		rows = append(rows, Row{name, formatKg(projection["total"]), formatPct(projection["confidence"]), formatNumber(projection["weeks_to_comp"], 1), text(projection["method"])})
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}

func (b block) alertRows() []Row {
	alerts := list(b.weekly["alerts"])
	if len(alerts) == 0 {
		return nil
	}
	rows := []Row{{"Severity", "Source", "Message", "Detail"}}
	for _, raw := range alerts {
		alert := record(raw)
		rows = append(rows, Row{text(alert["severity"]), text(alert["source"]), text(alert["message"]), text(alert["raw_detail"])})
	}
	return rows
}

func (b block) exerciseStatsRows() []Row {
	stats := record(b.weekly["exercise_stats"])
	if len(stats) == 0 {
		return nil
	}
	names := sortedKeys(stats)
	metric := func(name, key string) float64 {
		value, _ := number(record(stats[name])[key])
		return value
	}
	sort.SliceStable(names, func(a, c int) bool {
		left, right := names[a], names[c]
		if metric(left, "total_sets") != metric(right, "total_sets") {
			return metric(left, "total_sets") > metric(right, "total_sets")
		}
		return metric(left, "total_volume") > metric(right, "total_volume")
	})
	rows := []Row{{"Exercise", "Sets", "Volume", "Max kg"}}
	for _, name := range names {
		item := record(stats[name])
		rows = append(rows, Row{name, numberOrBlank(item["total_sets"]), formatKg(item["total_volume"]), formatKg(item["max_kg"])})
	}
	return rows
}

func evaluationRows(evaluation map[string]any) []Row {
	if evaluation == nil {
		return []Row{{"Section", "Text"}, {"Program Analysis", "No cached program analysis for this block."}}
	}
	summary := text(evaluation["summary"])
	if summary == "" {
		summary = text(evaluation["insufficient_data_reason"])
	}
	rows := []Row{{"Section", "Text"}, {"Summary", summary}}
	sections := []struct {
		label string
		key   string
	}{
		{"Working", "what_is_working"},
		{"Not Working", "what_is_not_working"},
		{"Adjustments", "small_changes"},
		{"Monitoring", "monitoring_focus"},
		{"Conclusion", "conclusion"},
	}
	for _, section := range sections {
		switch value := evaluation[section.key].(type) {
		case []any:
			for _, item := range value {
				rows = append(rows, Row{section.label, compact(item)})
			}
		default:
			if truthy(value) {
				rows = append(rows, Row{section.label, compact(value)})
			}
		}
	}
	return rows
}

func correlationRows(correlation map[string]any) []Row {
	headers := Row{"Exercise", "Lift", "Direction", "Strength", "Reasoning", "Caveat"}
	if correlation == nil {
		return []Row{headers, {"No cached ROI correlation report for this block.", "", "", "", "", ""}}
	}
	rows := []Row{headers}
	findings := list(correlation["findings"])
	if len(findings) == 0 {
		message := firstText(correlation["summary"], correlation["insufficient_data_reason"], "No findings.")
		return append(rows, Row{message, "", "", "", "", ""})
	}
	for _, raw := range findings {
		finding := record(raw)
		rows = append(rows, Row{
			text(finding["exercise"]), text(finding["lift"]), text(finding["correlation_direction"]),
			text(finding["strength"]), text(finding["reasoning"]), text(finding["caveat"]),
		})
	}
	return rows
}
