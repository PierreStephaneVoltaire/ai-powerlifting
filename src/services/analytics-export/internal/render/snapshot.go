package render

import (
	"sort"
	"time"
)

func (b block) inWindow(date string) bool {
	_, err := time.Parse("2006-01-02", date)
	start, end := text(b.meta["startDate"]), text(b.meta["endDate"])
	return err == nil && start != "" && end != "" && date >= start && date <= end
}

func (b block) bodyweightRows() []Row {
	weights := map[string]float64{}
	add := func(date string, value any) {
		if kg, ok := number(value); ok && kg > 0 && b.inWindow(date) {
			weights[date] = kg
		}
	}
	for _, raw := range list(b.bundle["weightLog"]) {
		entry := record(raw)
		add(text(entry["date"]), entry["kg"])
	}
	for _, session := range sortedSessions(sessionList(b.bundle["sessions"])) {
		sessionBlock, block := text(session["block"]), text(b.meta["block"])
		if text(session["status"]) != "skipped" && (sessionBlock == "" || block == "" || sessionBlock == block) {
			add(text(session["date"]), session["body_weight_kg"])
		}
	}
	if len(weights) == 0 {
		return nil
	}
	rows := []Row{{"Date", "Bodyweight"}}
	for _, date := range sortedKeysFloat(weights) {
		rows = append(rows, Row{date, formatBodyweight(weights[date])})
	}
	return rows
}

func sortedKeysFloat(values map[string]float64) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func (b block) nutritionRows() []Row {
	type bucket struct {
		sums              [6]float64
		counts            [6]int
		consistent, total int
		unit              string
	}
	weeks := map[string]*bucket{}
	fields := []string{"avg_daily_calories", "avg_protein_g", "avg_carb_g", "avg_fat_g", "water_intake", "avg_sleep_hours"}
	for _, raw := range list(b.bundle["dietNotes"]) {
		note := record(raw)
		date := text(note["date"])
		if !b.inWindow(date) {
			continue
		}
		if private, _ := note["private"].(bool); private {
			continue
		}
		day, _ := time.Parse("2006-01-02", date)
		week := day.AddDate(0, 0, -(int(day.Weekday())+6)%7).Format("2006-01-02")
		item := weeks[week]
		if item == nil {
			item = &bucket{}
			weeks[week] = item
		}
		for i, field := range fields {
			if value, ok := number(note[field]); ok {
				item.sums[i] += value
				item.counts[i]++
			}
		}
		if consistent, _ := note["consistent"].(bool); consistent {
			item.consistent++
		}
		item.total++
		if item.unit == "" {
			item.unit = firstText(note["water_unit"], "litres")
		}
	}
	if len(weeks) == 0 {
		return nil
	}
	keys := make([]string, 0, len(weeks))
	for key := range weeks {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	rows := []Row{{"Week starting", "Calories/day", "Protein g/day", "Carbs g/day", "Fat g/day", "Water/day", "Water unit", "Sleep hours/night", "Consistency"}}
	for _, week := range keys {
		item := weeks[week]
		values := make([]any, len(fields))
		for i := range fields {
			if item.counts[i] > 0 {
				values[i] = item.sums[i] / float64(item.counts[i])
			}
		}
		rows = append(rows, Row{week, values[0], values[1], values[2], values[3], values[4], item.unit, values[5], formatRawPct(float64(item.consistent) * 100 / float64(item.total))})
	}
	return rows
}

func (b block) measurementRows() []Row {
	meta := record(b.bundle["measurements"])
	rows := []Row{{"Measurement", "cm"}}
	for _, field := range []struct{ key, label string }{{"height_cm", "Height"}, {"arm_wingspan_cm", "Arm wingspan"}, {"leg_length_cm", "Leg length"}} {
		if value, ok := number(meta[field.key]); ok && value > 0 {
			rows = append(rows, Row{field.label, value})
		}
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}

func (b block) profileRows() []Row {
	rows := []Row{{"Lift", "Volume tolerance"}}
	for _, raw := range list(b.bundle["liftProfiles"]) {
		profile := record(raw)
		rows = append(rows, Row{text(profile["lift"]), text(profile["volume_tolerance"])})
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}
