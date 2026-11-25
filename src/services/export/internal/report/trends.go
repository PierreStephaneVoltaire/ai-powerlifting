package report

import (
	"math"
	"sort"
	"strconv"
	"strings"
	"time"

	"powerlifting/export/internal/calc"
)

type weightPoint struct {
	date string
	kg   float64
}
type weekTrend struct {
	week                           int
	date                           string
	weight, squat, bench, deadlift float64
}

func LiftTrends(sessions, weights []map[string]any, sex string) [][]any {
	return trendWeeks(sessions, weightPoints(sessions, weights), sex)
}

func BodyweightTrend(sessions, weights []map[string]any) [][]any {
	points := weightPoints(sessions, weights)
	rows := make([][]any, 0, len(points))
	for _, point := range points {
		rows = append(rows, []any{point.date, point.kg})
	}
	return rows
}

func weightPoints(sessions, weights []map[string]any) []weightPoint {
	byDate := map[string]float64{}
	add := func(date any, weight any) {
		day, ok := date.(string)
		if !ok || len(day) != 10 {
			return
		}
		if _, err := time.Parse("2006-01-02", day); err != nil {
			return
		}
		kg, ok := number(weight)
		if !ok || kg <= 0 || math.IsNaN(kg) || math.IsInf(kg, 0) {
			return
		}
		byDate[day] = kg
	}
	for _, entry := range weights {
		add(entry["date"], entry["kg"])
	}
	for _, session := range sessions {
		if session["status"] != "skipped" {
			add(session["date"], session["body_weight_kg"])
		}
	}
	points := make([]weightPoint, 0, len(byDate))
	for day, kg := range byDate {
		points = append(points, weightPoint{day, kg})
	}
	sort.Slice(points, func(i, j int) bool { return points[i].date < points[j].date })
	return points
}

func trendWeeks(sessions []map[string]any, weights []weightPoint, sex string) [][]any {
	weeks := map[int]*weekTrend{}
	for _, session := range sessions {
		if session["completed"] != true && session["status"] != "logged" && session["status"] != "completed" {
			continue
		}
		raw := session["week_number"]
		weekValue, numeric := number(raw)
		if raw == nil || raw == "" || numeric && weekValue == 0 {
			raw = session["week"]
		}
		week := 0
		switch value := raw.(type) {
		case string:
			if value != "" && strings.Trim(value, "0123456789") == "" {
				week, _ = strconv.Atoi(value)
			}
		default:
			if n, ok := number(value); ok && n == math.Trunc(n) {
				week = int(n)
			}
		}
		if week < 1 {
			continue
		}
		bucket := weeks[week]
		if bucket == nil {
			bucket = &weekTrend{week: week}
			weeks[week] = bucket
		}
		date, _ := session["date"].(string)
		if date != "" && (bucket.date == "" || date < bucket.date) {
			bucket.date = date
		}
		if weight, ok := number(session["body_weight_kg"]); ok && weight > bucket.weight && !math.IsInf(weight, 0) {
			bucket.weight = weight
		}
		for _, exercise := range records(session["exercises"]) {
			if exercise["rep_unit"] == "minutes" || exercise["rep_unit"] == "seconds" || exercise["duration_minutes"] != nil {
				continue
			}
			statuses, _ := exercise["set_statuses"].([]any)
			if len(statuses) > 0 {
				done := false
				for _, status := range statuses {
					if status == "completed" || status == "failed" {
						done = true
						break
					}
				}
				if !done {
					continue
				}
			} else if count, ok := number(exercise["sets"]); !ok || count == 0 {
				continue
			}
			weight, weightOK := number(exercise["kg"])
			reps, repsOK := number(exercise["reps"])
			if !weightOK || !repsOK {
				continue
			}
			var rpe *float64
			value := exercise["rpe"]
			if value == nil {
				value = session["session_rpe"]
			}
			if value != nil {
				parsed, ok := number(value)
				if !ok {
					continue
				}
				rpe = &parsed
			}
			estimate, ok := calc.EstimatedMax(weight, reps, rpe)
			if !ok {
				continue
			}
			name, _ := exercise["name"].(string)
			name = strings.ToLower(name)
			switch {
			case strings.Contains(name, "squat") && !strings.Contains(name, "hack") && !strings.Contains(name, "split"):
				bucket.squat = math.Max(bucket.squat, estimate)
			case name == "bench" || name == "bench press":
				bucket.bench = math.Max(bucket.bench, estimate)
			case strings.Contains(name, "deadlift") && !strings.Contains(name, "romanian") && !strings.Contains(name, "rdl"):
				bucket.deadlift = math.Max(bucket.deadlift, estimate)
			}
		}
	}
	order := make([]int, 0, len(weeks))
	for week := range weeks {
		order = append(order, week)
	}
	sort.Ints(order)
	rows := [][]any{}
	var previous *weekTrend
	for _, week := range order {
		b := weeks[week]
		total := calc.Round(b.squat+b.bench+b.deadlift, 1)
		if total == 0 {
			continue
		}
		weight := b.weight
		if weight == 0 {
			for _, point := range weights {
				if point.date <= b.date {
					weight = point.kg
				} else {
					break
				}
			}
		}
		var dots, score, mode any
		if weight > 0 {
			if result, err := calc.Dots(total, weight, sex); err == nil {
				dots = result
			}
		}
		modeKey, modeLabel := "", ""
		if b.squat > 0 && b.bench > 0 && b.deadlift > 0 {
			modeKey, modeLabel = "classic_powerlifting", "Classic"
		} else if b.bench > 0 && b.squat == 0 && b.deadlift == 0 {
			modeKey, modeLabel = "classic_bench", "Bench"
		}
		if modeKey != "" {
			if result, ok := calc.IPFScore(total, weight, sex, modeKey); ok {
				score, mode = result, modeLabel
			}
		}
		deltas := []any{nil, nil, nil}
		if previous != nil && previous.week == week-1 {
			for i, pair := range [][2]float64{{b.squat, previous.squat}, {b.bench, previous.bench}, {b.deadlift, previous.deadlift}} {
				if pair[0] != 0 && pair[1] != 0 {
					deltas[i] = calc.Round(pair[0]-pair[1], 1)
				}
			}
		}
		optional := func(v float64) any {
			if v == 0 {
				return nil
			}
			return v
		}
		rows = append(rows, []any{week, optional(b.squat), optional(b.bench), optional(b.deadlift), total, optional(calc.Round(weight, 2)), dots, score, mode, deltas[0], deltas[1], deltas[2]})
		previous = b
	}
	return rows
}

func Trends(sessions, weights, notes []map[string]any, sex string) [][]any {
	points := weightPoints(sessions, weights)
	rows := [][]any{{"Bodyweight Trend"}}
	if len(points) == 0 {
		rows = append(rows, []any{"Status", "No bodyweight data"})
	} else {
		oldest, latest := points[0].kg, points[len(points)-1].kg
		change := calc.Round(latest-oldest, 2)
		direction := "stable"
		if change > 0.25 {
			direction = "gain"
		} else if change < -0.25 {
			direction = "loss"
		}
		rows = append(rows, []any{"Latest", calc.Round(latest, 2)}, []any{"Oldest", calc.Round(oldest, 2)}, []any{"Change", change}, []any{"Direction", direction}, []any{"Entries", len(points)}, nil, []any{"Date", "Bodyweight (kg)"})
		for _, point := range points {
			rows = append(rows, []any{point.date, calc.Round(point.kg, 2)})
		}
	}
	rows = append(rows, nil, []any{"Nutrition Trend"})
	if len(notes) == 0 {
		rows = append(rows, []any{"No nutrition data recorded"})
	} else {
		count := 0
		for _, note := range notes {
			if note["consistent"] == true {
				count++
			}
		}
		rows = append(rows, []any{"Consistency %", calc.Round(float64(count)*100/float64(len(notes)), 1)})
		for _, field := range []metric{{"Calories", "avg_daily_calories"}, {"Protein", "avg_protein_g"}, {"Carbs", "avg_carb_g"}, {"Fat", "avg_fat_g"}, {"Sleep", "avg_sleep_hours"}, {"Water", "water_intake"}} {
			rows = append(rows, []any{field.label, average(notes, field.key)})
		}
		rows = append(rows, nil, []any{"Date", "Notes", "Calories", "Protein", "Carbs", "Fat", "Sleep", "Water", "Water Unit", "Consistent"})
		ordered := append([]map[string]any{}, notes...)
		sort.SliceStable(ordered, func(i, j int) bool {
			a, _ := ordered[i]["date"].(string)
			b, _ := ordered[j]["date"].(string)
			return a < b
		})
		for _, note := range ordered {
			rows = append(rows, []any{note["date"], note["notes"], note["avg_daily_calories"], note["avg_protein_g"], note["avg_carb_g"], note["avg_fat_g"], note["avg_sleep_hours"], note["water_intake"], note["water_unit"], note["consistent"]})
		}
	}
	rows = append(rows, nil, []any{"DOTS Trend"}, []any{"Week", "Squat (kg)", "Bench (kg)", "Deadlift (kg)", "Total (kg)", "Bodyweight (kg)", "DOTS", "IPF GL", "IPF GL mode", "Squat change (kg)", "Bench change (kg)", "Deadlift change (kg)"})
	trends := trendWeeks(sessions, points, sex)
	if len(trends) == 0 {
		rows = append(rows, []any{"No DOTS trend data available"})
	} else {
		rows = append(rows, trends...)
	}
	return rows
}
