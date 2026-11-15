package markdown

import (
	"fmt"
	"sort"
	"strings"

	"powerlifting/program/internal/calc"
	"powerlifting/program/internal/pyval"
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
	Weekly *weeklyView
	Dots   *dotsView
	Weight *weightTrendView
}

func (d sectionData) analysisSection() any {
	weekly := d.weekly
	hasTrends := len(d.sessions) > 0
	if len(weekly) == 0 && !hasTrends {
		return nil
	}
	view := analysisView{}
	if len(weekly) > 0 {
		view.Weekly = buildWeekly(weekly, d.liftOrder)
	}
	if rows := d.dotsTrendRows(); len(rows) > 0 {
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

type dotsRow struct {
	week       any
	squat      float64
	bench      float64
	deadlift   float64
	total      float64
	bodyweight any
	dots       any
}

func (d sectionData) dotsTrendRows() []dotsRow {
	type bucket struct {
		week                       any
		squat, bench, deadlift, bw float64
	}
	buckets := map[string]*bucket{}
	var order []string
	for _, session := range d.sessions {
		status := session["status"]
		if !truthy(session["completed"]) && status != "logged" && status != "completed" {
			continue
		}
		week := firstTruthy(session["week_number"], session["week"], int64(0))
		key := fmt.Sprintf("%T:%s", week, str(week))
		current := buckets[key]
		if current == nil {
			current = &bucket{week: week}
			buckets[key] = current
			order = append(order, key)
		}
		if bw := session["body_weight_kg"]; !blank(bw) {
			if value, _ := floatOf(bw); value > current.bw {
				current.bw = value
			}
		}
		for _, exercise := range maps(session["exercises"]) {
			name := strings.ToLower(str(getd(exercise, "name", "")))
			weight, reps := exercise["kg"], exercise["reps"]
			if blank(weight) || blank(reps) {
				continue
			}
			estimate := epley(weight, reps)
			switch {
			case strings.Contains(name, "squat") && !strings.Contains(name, "hack") && !strings.Contains(name, "split"):
				current.squat = maxFloat(current.squat, estimate)
			case strings.Contains(name, "bench"):
				current.bench = maxFloat(current.bench, estimate)
			case strings.Contains(name, "deadlift") && !strings.Contains(name, "romanian") && !strings.Contains(name, "rdl"):
				current.deadlift = maxFloat(current.deadlift, estimate)
			}
		}
	}
	sort.SliceStable(order, func(i, j int) bool {
		wi, wj := buckets[order[i]].week, buckets[order[j]].week
		ni, oki := intOf(wi)
		nj, okj := intOf(wj)
		if _, isString := wi.(string); isString {
			oki = isDigits(wi.(string))
		}
		if _, isString := wj.(string); isString {
			okj = isDigits(wj.(string))
		}
		switch {
		case oki && okj:
			return ni < nj
		case oki:
			return true
		case okj:
			return false
		}
		return str(wi) < str(wj)
	})
	rows := make([]dotsRow, 0, len(order))
	for _, key := range order {
		b := buckets[key]
		total := calc.Round(b.squat+b.bench+b.deadlift, 1)
		var bodyweight any
		if b.bw != 0 {
			bodyweight = b.bw
		} else {
			bodyweight = firstNonBlank(d.meta["current_body_weight_kg"], d.meta["bodyweight_kg"], "")
		}
		var dots any = ""
		if total != 0 && truthy(bodyweight) {
			dots = dotsValue(total, bodyweight, d.sex)
		}
		row := dotsRow{week: b.week, squat: calc.Round(b.squat, 1), bench: calc.Round(b.bench, 1), deadlift: calc.Round(b.deadlift, 1), total: total, dots: dots}
		if truthy(bodyweight) {
			row.bodyweight = num(bodyweight)
		} else {
			row.bodyweight = ""
		}
		rows = append(rows, row)
	}
	return rows
}

func maxFloat(a, b float64) float64 {
	if b > a {
		return b
	}
	return a
}

func floatOrBlank(value float64) any {
	if value == 0 {
		return ""
	}
	return value
}

func buildDots(rows []dotsRow) *dotsView {
	view := &dotsView{}
	var withDots []dotsRow
	for _, row := range rows {
		if !blank(row.dots) {
			withDots = append(withDots, row)
		}
	}
	if len(withDots) >= 2 {
		first, last := withDots[0], withDots[len(withDots)-1]
		firstValue, _ := floatOf(first.dots)
		lastValue, _ := floatOf(last.dots)
		change := calc.Round(lastValue-firstValue, 2)
		span := len(withDots)
		direction := ""
		if change >= 0 {
			direction = "+"
		}
		perWeek := calc.Round(change/float64(max(1, span-1)), 2)
		view.Change = fmt.Sprintf("DOTS %s%s over %d tracked weeks (%s%s/week).", direction, pyval.FloatRepr(change), span, direction, pyval.FloatRepr(perWeek))
	}
	var tableRows [][]any
	for _, row := range rows {
		tableRows = append(tableRows, []any{"W" + str(row.week), floatOrBlank(row.squat), floatOrBlank(row.bench), floatOrBlank(row.deadlift), floatOrBlank(row.total), orBlank(row.bodyweight), orBlank(row.dots)})
	}
	view.Table = table([]string{"Week", "Squat", "Bench", "Deadlift", "Total", "BW", "DOTS"}, tableRows)
	return view
}

func orBlank(value any) any {
	if !truthy(value) {
		return ""
	}
	return value
}

func (d sectionData) weightTrend() *weightTrendView {
	type point struct {
		date string
		kg   float64
	}
	var points []point
	if len(d.weightLog) > 0 {
		for _, entry := range sortedStable(d.weightLog, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) }) {
			if kg := entry["kg"]; !blank(kg) {
				value, _ := floatOf(kg)
				points = append(points, point{str(getd(entry, "date", "")), value})
			}
		}
	} else {
		for _, session := range d.sessions {
			if !truthy(session["completed"]) {
				continue
			}
			if bw := session["body_weight_kg"]; !blank(bw) {
				value, _ := floatOf(bw)
				points = append(points, point{str(getd(session, "date", "")), value})
			}
		}
	}
	if len(points) < 2 {
		return nil
	}
	oldest, latest := points[0], points[len(points)-1]
	change := calc.Round(latest.kg-oldest.kg, 1)
	direction := "stable"
	if change > 0.25 {
		direction = "gain"
	} else if change < -0.25 {
		direction = "loss"
	}
	sign := ""
	if change > 0 {
		sign = "+"
	}
	view := &weightTrendView{Summary: fmt.Sprintf("**%s kg** (%s%s kg over %d entries, %s). Started at %s kg on %s.", pyval.FloatRepr(latest.kg), sign, pyval.FloatRepr(change), len(points), direction, pyval.FloatRepr(oldest.kg), oldest.date)}
	if len(points) > 2 {
		shown := points[max(0, len(points)-12):]
		var rows [][]any
		prev := 0.0
		hasPrev := false
		for _, p := range shown {
			delta := ""
			if hasPrev {
				delta = signed(calc.Round(p.kg-prev, 1))
			}
			rows = append(rows, []any{p.date, p.kg, delta})
			prev, hasPrev = p.kg, true
		}
		view.Table = table([]string{"Date", "Weight (kg)", "Change"}, rows)
	}
	return view
}

func orderedKeys(values M, order []string) []string {
	if len(order) == len(values) {
		complete := true
		for _, key := range order {
			if _, ok := values[key]; !ok {
				complete = false
			}
		}
		if complete {
			return order
		}
	}
	return pyval.SortedKeys(values)
}
