package render

import "strings"

func formatBodyweight(value any) string {
	if n, ok := number(value); ok {
		return strings.TrimRight(strings.TrimRight(fixed(n, 2), "0"), ".") + " kg"
	}
	return "--"
}

func seriesRows(value any, headings Row, keys ...string) []Row {
	rows := []Row{headings}
	for _, raw := range list(value) {
		point := record(raw)
		row := make(Row, len(keys))
		for i, key := range keys {
			row[i] = point[key]
		}
		rows = append(rows, row)
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}

func (b block) banisterRows() []Row {
	banister := record(b.weekly["banister"])
	rows := seriesRows(banister["series"], Row{"Date", "Fitness (CTL)", "Fatigue (ATL)", "Form (TSB)"}, "date", "ctl", "atl", "tsb")
	if len(rows) == 0 {
		return nil
	}
	start, end := text(b.meta["startDate"]), text(b.meta["endDate"])
	filtered := rows[:1]
	for _, row := range rows[1:] {
		date := text(row[0])
		if (start == "" || date >= start) && (end == "" || date <= end) {
			filtered = append(filtered, row)
		}
	}
	if len(filtered) == 1 {
		return nil
	}
	return filtered
}

func (b block) timelineRows() []Row {
	return seriesRows(record(b.weekly["peaking_timeline"])["series"], Row{"Date", "Actual TSB", "Projected TSB"}, "date", "actual_tsb", "projected_tsb")
}

func (b block) timelineSpecificityRows() []Row {
	return seriesRows(record(b.weekly["peaking_timeline"])["specificity_points"], Row{"Date", "Narrow", "Broad", "Weeks to competition"}, "date", "narrow", "broad", "weeks_to_comp")
}

func (b block) decouplingRows() []Row {
	return seriesRows(record(b.weekly["decoupling"])["series"], Row{"Week starting", "Decoupling", "e1RM slope %/week", "Fatigue slope points/week"}, "week_start", "decoupling", "e1rm_slope_pct_per_week", "fi_slope_pct_points_per_week")
}

func (b block) taperRows() []Row {
	taper := record(b.weekly["taper_quality"])
	if len(taper) == 0 || taper["status"] == "insufficient_data" {
		return nil
	}
	components := record(taper["components"])
	return []Row{{"Metric", "Value"}, {"Score", taper["score"]}, {"Label", taper["label"]}, {"Weeks to competition", taper["weeks_to_comp"]}, {"Volume reduction", formatPct(components["volume_reduction"])}, {"Intensity maintained", formatPct(components["intensity_maintained"])}, {"Fatigue trend", formatPct(components["fatigue_trend"])}, {"TSB", formatPct(components["tsb"])}}
}

func (b block) landmarkRows() []Row {
	landmarks := record(b.weekly["volume_landmarks"])
	rows := []Row{{"Lift", "MV", "MEV", "MAV", "MRV", "Confidence"}}
	for _, lift := range sortedKeys(landmarks) {
		item := record(landmarks[lift])
		if item["status"] == "insufficient_data" {
			continue
		}
		rows = append(rows, Row{titleize(lift), item["mv"], item["mev"], item["mav"], item["mrv"], item["confidence"]})
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}
