package report

import (
	"encoding/json"
	"math"
	"sort"
	"time"
)

type Table struct {
	Title   string
	Headers []string
	Rows    [][]any
}

type metric struct{ label, key string }

var nutritionMetrics = []metric{
	{"Calories", "avg_daily_calories"}, {"Protein (g)", "avg_protein_g"},
	{"Carbs (g)", "avg_carb_g"}, {"Fat (g)", "avg_fat_g"},
	{"Sleep (hours)", "avg_sleep_hours"}, {"Water", "water_intake"},
}

func number(value any) (float64, bool) {
	switch n := value.(type) {
	case json.Number:
		f, err := n.Float64()
		return f, err == nil
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	default:
		return 0, false
	}
}

func average(rows []map[string]any, key string) any {
	var sum float64
	count := 0
	for _, row := range rows {
		if value, ok := number(row[key]); ok {
			sum += value
			count++
		}
	}
	if count == 0 {
		return nil
	}
	return math.RoundToEven(sum/float64(count)*10) / 10
}

func NutritionTables(notes []map[string]any, meta map[string]any) []Table {
	weekday := time.Monday
	current, _ := meta["current_block_id"].(string)
	if blocks, ok := meta["blocks"].([]any); ok {
		for _, raw := range blocks {
			block, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			id, _ := block["id"].(string)
			if id == "" {
				id, _ = block["block_id"].(string)
			}
			if id != current {
				continue
			}
			name, _ := block["week_start_day"].(string)
			for i := time.Sunday; i <= time.Saturday; i++ {
				if i.String() == name {
					weekday = i
					break
				}
			}
			break
		}
	}
	weeks := map[time.Time][]map[string]any{}
	for _, note := range notes {
		value, _ := note["date"].(string)
		date, err := time.Parse("2006-01-02", value)
		if err != nil {
			continue
		}
		week := date.AddDate(0, 0, -(int(date.Weekday())-int(weekday)+7)%7)
		weeks[week] = append(weeks[week], note)
	}
	if len(weeks) == 0 {
		return nil
	}
	dates := make([]time.Time, 0, len(weeks))
	for date := range weeks {
		dates = append(dates, date)
	}
	sort.Slice(dates, func(i, j int) bool { return dates[i].Before(dates[j]) })
	rows := make([][]any, 0, len(dates))
	scoped := []map[string]any{}
	for _, date := range dates {
		entries := weeks[date]
		scoped = append(scoped, entries...)
		row := []any{date.Format("2006-01-02")}
		for _, m := range nutritionMetrics {
			row = append(row, average(entries, m.key))
		}
		count := 0
		var unit any
		for _, entry := range entries {
			if consistent, ok := entry["consistent"].(bool); ok && consistent {
				count++
			}
			if unit == nil {
				if value, ok := entry["water_unit"].(string); ok && value != "" {
					unit = value
				}
			}
		}
		row = append(row, math.RoundToEven(100*float64(count)/float64(len(entries))), unit)
		rows = append(rows, row)
	}
	summary := [][]any{}
	for i, m := range nutritionMetrics {
		var values []float64
		for _, row := range rows {
			if value, ok := row[i+1].(float64); ok {
				values = append(values, value)
			}
		}
		if len(values) == 0 {
			continue
		}
		var change any
		if len(values) > 1 {
			change = math.RoundToEven((values[len(values)-1]-values[0])/float64(len(values)-1)*10) / 10
		}
		summary = append(summary, []any{m.label, average(scoped, m.key), change})
	}
	tables := []Table{}
	if len(summary) > 0 {
		tables = append(tables, Table{"Nutrition and Sleep", []string{"Metric", "Average", "Change/week"}, summary})
	}
	headers := []string{"Week starting"}
	for _, m := range nutritionMetrics {
		headers = append(headers, m.label)
	}
	headers = append(headers, "Consistency (%)", "Water unit")
	return append(tables, Table{"Weekly Nutrition and Sleep", headers, rows})
}
