package markdown

import (
	"math"
	"time"

	"powerlifting/export/internal/calc"
)

func parseDate(value string) (time.Time, bool) {
	if value == "" {
		return time.Time{}, false
	}
	if len(value) > 10 {
		value = value[:10]
	}
	parsed, err := time.Parse("2006-01-02", value)
	return parsed, err == nil
}

func dateText(value any) string { return str(value) }

func daysBetween(a, b time.Time) int {
	return int(math.Abs(a.Sub(b).Hours() / 24))
}

func nearestWeightLog(target time.Time, hasTarget bool, weightLog []M) any {
	if !hasTarget || len(weightLog) == 0 {
		return ""
	}
	best := -1
	var bestValue any
	for _, entry := range weightLog {
		date, ok := parseDate(dateText(getd(entry, "date", "")))
		if !ok || blank(entry["kg"]) {
			continue
		}
		delta := daysBetween(date, target)
		if best < 0 || delta < best {
			best, bestValue = delta, entry["kg"]
		}
	}
	if best < 0 {
		return ""
	}
	return bestValue
}

func metaBodyweight(meta M) any {
	return firstNonBlank(meta["current_body_weight_kg"], meta["bodyweight_kg"])
}

func resolveSessionBodyweight(sessions []M, index int, weightLog []M, meta M) (any, string) {
	session := sessions[index]
	if !blank(session["body_weight_kg"]) {
		return num(session["body_weight_kg"]), "session"
	}
	prevDistance, nextDistance := 0, 0
	var prev, next any
	for offset := 1; offset < len(sessions); offset++ {
		left, right := index-offset, index+offset
		if prev == nil && left >= 0 && !blank(sessions[left]["body_weight_kg"]) {
			prev, prevDistance = sessions[left]["body_weight_kg"], offset
		}
		if next == nil && right < len(sessions) && !blank(sessions[right]["body_weight_kg"]) {
			next, nextDistance = sessions[right]["body_weight_kg"], offset
		}
		if prev != nil && next != nil {
			break
		}
	}
	switch {
	case prev != nil && next != nil:
		if prevDistance <= nextDistance {
			return num(prev), "previous session"
		}
		return num(next), "next session"
	case prev != nil:
		return num(prev), "previous session"
	case next != nil:
		return num(next), "next session"
	}
	date, ok := parseDate(dateText(getd(session, "date", "")))
	if value := nearestWeightLog(date, ok, weightLog); !blank(value) {
		return num(value), "weight log"
	}
	if fallback := metaBodyweight(meta); !blank(fallback) {
		return num(fallback), "meta"
	}
	return 0.0, "fallback"
}

func resolveDateBodyweight(target any, sessions []M, weightLog []M, meta M) (any, string) {
	text, _ := target.(string)
	parsed, ok := parseDate(text)
	if !ok {
		if fallback := metaBodyweight(meta); !blank(fallback) {
			return num(fallback), "meta"
		}
		return 0.0, "fallback"
	}
	bestDelta := -1
	var bestValue any
	for _, session := range sessions {
		if blank(session["body_weight_kg"]) {
			continue
		}
		date, ok := parseDate(dateText(getd(session, "date", "")))
		if !ok {
			continue
		}
		delta := daysBetween(date, parsed)
		if bestDelta < 0 || delta < bestDelta {
			bestDelta, bestValue = delta, session["body_weight_kg"]
		}
	}
	if bestDelta >= 0 {
		return num(bestValue), "session"
	}
	if value := nearestWeightLog(parsed, true, weightLog); !blank(value) {
		return num(value), "weight log"
	}
	if fallback := metaBodyweight(meta); !blank(fallback) {
		return num(fallback), "meta"
	}
	return 0.0, "fallback"
}

func phaseNameOf(value any) string {
	if phase, ok := value.(map[string]any); ok {
		if name, present := phase["name"]; present {
			return str(name)
		}
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return str(value)
}

func prepareSessions(sessions []M, weightLog []M, meta M, phases []M) []M {
	ordered := sortedStable(sessions, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) })
	for index, session := range ordered {
		status := firstNonBlank(session["status"], completedOrPlanned(session))
		completed := truthy(session["completed"]) || status == "logged" || status == "completed"
		session["status"] = status
		session["completed"] = completed
		session["body_weight_kg"], session["body_weight_source"] = resolveSessionBodyweight(ordered, index, weightLog, meta)
		session["block"] = firstNonBlank(session["block"], "current")
		phaseName := phaseNameOf(getd(session, "phase", ""))
		week := session["week_number"]
		if !truthy(week) {
			week = session["week"]
		}
		if len(phases) > 0 && week != nil {
			if weekNumber, ok := intOf(week); ok {
				for _, phase := range phases {
					start, okStart := intOf(getd(phase, "start_week", int64(0)))
					end, okEnd := intOf(getd(phase, "end_week", int64(0)))
					if !okStart || !okEnd {
						continue
					}
					if start <= weekNumber && weekNumber <= end {
						if name := phaseNameOf(getd(phase, "name", "")); name != "" {
							phaseName = name
						}
						break
					}
				}
			}
		}
		session["phase_name"] = phaseName
		if wellness, ok := session["wellness"].(map[string]any); ok && len(wellness) > 0 {
			session["wellness"] = M{
				"sleep": wellness["sleep"], "soreness": wellness["soreness"], "mood": wellness["mood"],
				"stress": wellness["stress"], "energy": wellness["energy"], "recorded_at": wellness["recorded_at"],
			}
		}
	}
	return ordered
}

func completedOrPlanned(session M) string {
	if truthy(session["completed"]) {
		return "completed"
	}
	return "planned"
}

func dotsValue(total, bodyweight any, sex string) any {
	if blank(total) || blank(bodyweight) {
		return ""
	}
	t, okT := floatOf(total)
	b, okB := floatOf(bodyweight)
	if !okT || !okB {
		return ""
	}
	value, err := calc.Dots(t, b, sex)
	if err != nil {
		return ""
	}
	return value
}

func resolveTotal(payload M) any {
	if total := payload["total_kg"]; !blank(total) {
		return total
	}
	lifts := []any{payload["squat_kg"], payload["bench_kg"], payload["deadlift_kg"]}
	for _, lift := range lifts {
		if blank(lift) {
			return ""
		}
	}
	sum := 0.0
	for _, lift := range lifts {
		value, ok := floatOf(lift)
		if !ok {
			return ""
		}
		sum += value
	}
	return calc.Round(sum, 1)
}

func PrepareSessions(program map[string]any, weightLog []map[string]any) []map[string]any {
	return prepareSessions(maps(program["sessions"]), weightLog, asMap(program["meta"]), maps(program["phases"]))
}

func ResolveBodyweightForDate(date any, sessions, weights []map[string]any, meta map[string]any) (any, string) {
	return resolveDateBodyweight(date, sessions, weights, meta)
}
