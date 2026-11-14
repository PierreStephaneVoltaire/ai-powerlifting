package session

import (
	"regexp"
	"strconv"

	"powerlifting/sessions/internal/value"
)

const (
	defaultBlock = "current"
	unscheduled  = "Unscheduled"
)

var weekPattern = regexp.MustCompile(`(?i)W(\d+)`)

func parseWeek(session value.Item) int {
	if parsed := value.IntOf(session["week_number"], -1); parsed >= 0 {
		return parsed
	}
	week := session["week"]
	if text, ok := week.(string); ok {
		if match := weekPattern.FindStringSubmatch(text); match != nil {
			if n, err := strconv.Atoi(match[1]); err == nil {
				return n
			}
		}
	}
	return value.IntOf(week, 0)
}

func blockOf(record value.Item) string {
	return value.Str(value.Or(record["block"], defaultBlock))
}

func unscheduledPhase(week int, block string) value.Item {
	return value.Item{
		"name":       unscheduled,
		"intent":     "",
		"start_week": value.Int(week),
		"end_week":   value.Int(week),
		"block":      block,
	}
}

func resolvePhase(session value.Item, phases []any) value.Item {
	week := parseWeek(session)
	block := blockOf(session)
	if phases != nil {
		for _, candidate := range phases {
			phase, ok := value.Map(candidate)
			if !ok || blockOf(phase) != block {
				continue
			}
			if value.IntOf(phase["start_week"], 0) <= week && week <= value.IntOf(phase["end_week"], 0) {
				return value.CopyItem(phase)
			}
		}
		return unscheduledPhase(week, block)
	}
	switch existing := session["phase"].(type) {
	case map[string]any:
		if len(existing) > 0 {
			phase := value.CopyItem(existing)
			if _, present := phase["block"]; !present {
				phase["block"] = block
			}
			return phase
		}
	case string:
		if existing != "" {
			return value.Item{"name": existing, "intent": "", "start_week": value.Int(week), "end_week": value.Int(week), "block": block}
		}
	}
	return unscheduledPhase(week, block)
}

func phaseRef(phase value.Item) string {
	name := value.Str(value.Or(phase["name"], unscheduled))
	bounds := func(key string) string {
		if v, present := phase[key]; present {
			return value.Str(v)
		}
		return "0"
	}
	return "phase#" + blockOf(phase) + "#W" + bounds("start_week") + "-W" + bounds("end_week") + "#" + replaceHash(name)
}

func replaceHash(text string) string {
	out := []byte(text)
	for i, c := range out {
		if c == '#' {
			out[i] = '-'
		}
	}
	return string(out)
}
