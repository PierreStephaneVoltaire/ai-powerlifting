package projection

import (
	"encoding/json"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"powerlifting/competition/internal/pyval"
)

var weekLabel = regexp.MustCompile(`(?i)W(\d+)`)

func intValue(value any, fallback int64) int64 {
	switch typed := value.(type) {
	case float64:
		return int64(typed)
	case json.Number:
		parsed, err := typed.Float64()
		if err != nil {
			return fallback
		}
		return int64(parsed)
	case int:
		return int64(typed)
	case int64:
		return typed
	case string:
		parsed, err := strconv.ParseInt(strings.TrimSpace(typed), 10, 64)
		if err != nil {
			return fallback
		}
		return parsed
	}
	return fallback
}

func parseWeekNumber(item map[string]any) int64 {
	if parsed := intValue(item["week_number"], -1); parsed >= 0 {
		return parsed
	}
	if label, ok := item["week"].(string); ok {
		if match := weekLabel.FindStringSubmatch(label); match != nil {
			parsed, _ := strconv.ParseInt(match[1], 10, 64)
			return parsed
		}
	}
	return intValue(item["week"], 0)
}

func exerciseFromValue(value any) Exercise {
	object, _ := value.(map[string]any)
	name, _ := object["name"].(string)
	exercise := Exercise{
		Key:  NormalizeName(name),
		Kg:   numOf(object["kg"]),
		Reps: numOf(object["reps"]),
		Sets: numOf(object["sets"]),
	}
	if present(object["rpe"]) {
		rpe := numOf(object["rpe"])
		exercise.RPE = &rpe
	}
	if statuses, ok := object["set_statuses"].([]any); ok {
		for _, status := range statuses {
			text, _ := status.(string)
			exercise.Statuses = append(exercise.Statuses, text)
		}
	}
	return exercise
}

func SessionFromItem(item map[string]any) Session {
	dateText, _ := item["date"].(string)
	session := Session{DateText: dateText}
	if day, ok := ParseDay(dateText); ok {
		session.Date = &day
	}
	week := parseWeekNumber(item)
	session.WeekNumber = &week
	if present(item["status"]) {
		session.Status, _ = item["status"].(string)
	}
	session.Completed = pyval.Truthy(item["completed"]) || session.Status == "logged" || session.Status == "completed"
	if present(item["session_rpe"]) {
		rpe := numOf(item["session_rpe"])
		session.SessionRPE = &rpe
	}
	if exercises, ok := item["exercises"].([]any); ok {
		for _, exercise := range exercises {
			session.Exercises = append(session.Exercises, exerciseFromValue(exercise))
		}
	}
	return session
}

func SessionsFromItems(items []map[string]any) []Session {
	ordered := append([]map[string]any(nil), items...)
	sort.SliceStable(ordered, func(i, j int) bool { return lessSession(ordered[i], ordered[j]) })
	sessions := make([]Session, len(ordered))
	for index, item := range ordered {
		sessions[index] = SessionFromItem(item)
	}
	return sessions
}

func lessSession(a, b map[string]any) bool {
	if left, right := textOrEmpty(a["date"]), textOrEmpty(b["date"]); left != right {
		return left < right
	}
	if left, right := intValue(a["same_day_ordinal"], 0), intValue(b["same_day_ordinal"], 0); left != right {
		return left < right
	}
	if left, right := intValue(a["source_index"], 0), intValue(b["source_index"], 0); left != right {
		return left < right
	}
	return textOrEmpty(a["sk"]) < textOrEmpty(b["sk"])
}

func textOrEmpty(value any) string {
	if pyval.Truthy(value) {
		return pyval.Str(value)
	}
	return ""
}

func CompetitionFromEntry(entry map[string]any) (Competition, bool) {
	status := pyval.Or(entry["user_status"], entry["status"])
	if !pyval.Truthy(status) || status == "available" {
		return Competition{}, false
	}
	competition := Competition{Status: pyval.Str(status)}
	if date := pyval.Or(entry["start_date"], entry["date"]); pyval.Truthy(date) {
		competition.DateText = pyval.Str(date)
	}
	if day, ok := ParseDay(competition.DateText); ok {
		competition.Date = &day
	}
	competition.Results, _ = entry["results"].(map[string]any)
	return competition, true
}

func normalizedKey(entry map[string]any) (string, string) {
	masterID := pyval.Or(entry["master_id"], strings.TrimPrefix(textOrEmpty(entry["sk"]), "COMP#"))
	date := pyval.Or(entry["start_date"], entry["date"])
	return textOrEmpty(date), textOrEmpty(masterID)
}

func CompetitionsFromEntries(entries []map[string]any) []Competition {
	kept := make([]map[string]any, 0, len(entries))
	for _, entry := range entries {
		if _, ok := CompetitionFromEntry(entry); ok {
			kept = append(kept, entry)
		}
	}
	sort.SliceStable(kept, func(i, j int) bool {
		leftDate, leftID := normalizedKey(kept[i])
		rightDate, rightID := normalizedKey(kept[j])
		if leftDate != rightDate {
			return leftDate < rightDate
		}
		return leftID < rightID
	})
	competitions := make([]Competition, len(kept))
	for index, entry := range kept {
		competitions[index], _ = CompetitionFromEntry(entry)
	}
	return competitions
}
