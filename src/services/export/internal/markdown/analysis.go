package markdown

import (
	"fmt"
	"strings"

	"powerlifting/export/internal/calc"
	"powerlifting/export/internal/report"
	"powerlifting/export/internal/values"
)

type weeklyView struct {
	Lines       []string
	Alerts      []string
	Lifts       []string
	Projections []string
	Reason      string
}

type dotsView struct {
	Change string
	Table  string
}

type weightTrendView struct {
	Summary string
	Table   string
}

type analysisView struct {
	Details string
	AI      string
	Weekly  *weeklyView
	Dots    *dotsView
	Weight  *weightTrendView
}

func (d sectionData) analysisSection() any {
	weekly := d.weekly
	hasTrends := len(d.sessions) > 0
	if len(weekly) == 0 && !hasTrends && len(d.dietNotes) == 0 && len(d.correlation) == 0 && len(d.evaluation) == 0 {
		return nil
	}
	view := analysisView{}
	for _, item := range report.AnalysisTables(weekly, d.dietNotes, d.meta) {
		view.Details += "### " + item.Title + "\n\n" + table(item.Headers, item.Rows) + "\n\n"
	}
	view.AI = strings.TrimSpace(aiReports(d.correlation, d.evaluation))
	if len(weekly) > 0 {
		view.Weekly = buildWeekly(weekly, d.liftOrder)
	}
	if rows := report.LiftTrends(d.rawSessions, d.weightLog, d.sex); len(rows) > 0 {
		view.Dots = buildDots(rows)
	}
	view.Weight = d.weightTrend()
	return view
}

func buildWeekly(weekly M, liftOrder []string) *weeklyView {
	view := &weeklyView{}
	week := getd(weekly, "week", "")
	if truthy(week) {
		header := "Week " + str(week)
		if block := getd(weekly, "block", ""); truthy(block) {
			header += " of " + str(block)
		}
		line := "**" + header + ".**"
		if analyzed := getd(weekly, "sessions_analyzed", ""); truthy(analyzed) {
			line += " " + str(analyzed) + " sessions analyzed."
		}
		view.Lines = append(view.Lines, line)
	}
	if compliance := asMap(weekly["compliance"]); len(compliance) > 0 {
		planned, completed, pct := getd(compliance, "planned", ""), getd(compliance, "completed", ""), getd(compliance, "pct", "")
		if truthy(planned) && truthy(completed) {
			view.Lines = append(view.Lines, "Compliance: "+str(completed)+" of "+str(planned)+" planned sessions completed ("+str(pct)+"%).")
		}
	}
	if dots := weekly["estimated_dots"]; !blank(dots) {
		view.Lines = append(view.Lines, "Estimated DOTS: "+str(dots)+".")
	}
	if maxes := asMap(weekly["current_maxes"]); len(maxes) > 0 {
		var parts []string
		for _, lift := range []string{"squat", "bench", "deadlift"} {
			if value := maxes[lift]; !blank(value) {
				parts = append(parts, title(lift)+": "+str(value)+" kg")
			}
		}
		if len(parts) > 0 {
			view.Lines = append(view.Lines, "Current e1RM: "+strings.Join(parts, " / ")+".")
		}
	}
	if fatigue := weekly["fatigue_index"]; !blank(fatigue) {
		view.Lines = append(view.Lines, "Fatigue index: "+str(fatigue)+"/10.")
	}
	if readiness, ok := weekly["readiness_score"].(map[string]any); ok {
		score, zone := readiness["score"], readiness["zone"]
		if !blank(score) {
			if truthy(zone) {
				view.Lines = append(view.Lines, "Readiness: "+str(score)+"/100 ("+str(zone)+" zone).")
			} else {
				view.Lines = append(view.Lines, "Readiness: "+str(score)+"/100.")
			}
		}
	}
	if alerts, ok := weekly["alerts"].([]any); ok {
		for _, alert := range alerts {
			view.Alerts = append(view.Alerts, str(alert))
		}
	}
	if lifts := asMap(weekly["lifts"]); len(lifts) > 0 {
		for _, name := range orderedKeys(lifts, liftOrder) {
			data := asMap(lifts[name])
			parts := []string{name}
			if progression := data["progression_rate_kg_per_week"]; !blank(progression) {
				parts = append(parts, str(progression)+" kg/week")
			}
			if trend := data["rpe_trend"]; !blank(trend) {
				parts = append(parts, "RPE trend: "+str(trend))
			}
			view.Lifts = append(view.Lifts, strings.Join(parts, " — "))
		}
	}
	if projections, ok := weekly["projections"].([]any); ok && len(projections) > 0 {
		for _, raw := range projections {
			p := asMap(raw)
			parts := []string{"**" + str(firstTruthy(p["comp_name"], "Unscheduled")) + "**"}
			if value := p["weeks_to_comp"]; !blank(value) {
				parts = append(parts, str(value)+" weeks out")
			}
			if value := p["total"]; !blank(value) {
				parts = append(parts, "projected total: "+str(value)+" kg")
			}
			if value := p["confidence"]; !blank(value) {
				parts = append(parts, "confidence: "+str(value))
			}
			view.Projections = append(view.Projections, strings.Join(parts, " — "))
		}
	} else if reason := weekly["projection_reason"]; truthy(reason) {
		view.Reason = str(reason)
	}
	return view
}

func buildDots(rows [][]any) *dotsView {
	view := &dotsView{}
	var first, last float64
	count := 0
	tableRows := make([][]any, 0, len(rows))
	for _, row := range rows {
		copy := append([]any{}, row...)
		copy[0] = "W" + str(copy[0])
		tableRows = append(tableRows, copy)
		if value, ok := floatOf(row[6]); ok {
			if count == 0 {
				first = value
			}
			last = value
			count++
		}
	}
	if count >= 2 {
		change := calc.Round(last-first, 2)
		direction := ""
		if change >= 0 {
			direction = "+"
		}
		perWeek := calc.Round(change/float64(count-1), 2)
		view.Change = fmt.Sprintf("DOTS %s%s over %d tracked weeks (%s%s/week).", direction, values.FloatRepr(change), count, direction, values.FloatRepr(perWeek))
	}
	view.Table = table([]string{"Week", "Squat (kg)", "Bench (kg)", "Deadlift (kg)", "Total (kg)", "Bodyweight (kg)", "DOTS", "IPF GL", "IPF GL mode", "Squat change (kg)", "Bench change (kg)", "Deadlift change (kg)"}, tableRows)
	return view
}

func (d sectionData) weightTrend() *weightTrendView {
	points := report.BodyweightTrend(d.rawSessions, d.weightLog)
	if len(points) == 0 {
		return nil
	}
	oldest, latest := points[0], points[len(points)-1]
	first, _ := floatOf(oldest[1])
	last, _ := floatOf(latest[1])
	change := calc.Round(last-first, 2)
	direction := "stable"
	if change > .25 {
		direction = "gain"
	} else if change < -.25 {
		direction = "loss"
	}
	sign := ""
	if change > 0 {
		sign = "+"
	}
	view := &weightTrendView{Summary: fmt.Sprintf("**%s kg** (%s%s kg over %d entries, %s). Started at %s kg on %s.", values.FloatRepr(last), sign, values.FloatRepr(change), len(points), direction, values.FloatRepr(first), oldest[0])}
	rows := make([][]any, 0, len(points))
	for i, point := range points {
		var delta any
		if i > 0 {
			prior, _ := floatOf(points[i-1][1])
			current, _ := floatOf(point[1])
			delta = calc.Round(current-prior, 2)
		}
		rows = append(rows, []any{point[0], point[1], delta})
	}
	view.Table = table([]string{"Date", "Weight (kg)", "Change (kg)"}, rows)
	return view
}

func orderedKeys(items M, order []string) []string {
	if len(order) == len(items) {
		complete := true
		for _, key := range order {
			if _, ok := items[key]; !ok {
				complete = false
			}
		}
		if complete {
			return order
		}
	}
	return values.SortedKeys(items)
}
