package payload

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

var weekdays = []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}

func text(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}
func integer(value any, fallback int) int {
	switch n := value.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case json.Number:
		i, err := n.Int64()
		if err == nil {
			return int(i)
		}
	case string:
		i, err := strconv.Atoi(n)
		if err == nil {
			return i
		}
	}
	return fallback
}
func setDefault(m map[string]any, key string, value any) {
	if _, ok := m[key]; !ok {
		m[key] = value
	}
}
func keys(values map[string]bool) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}
func uuid() (string, error) {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "", err
	}
	bytes[6] = bytes[6]&0x0f | 0x40
	bytes[8] = bytes[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", bytes[:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:]), nil
}

func Clone(input map[string]any) (map[string]any, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func Prepare(input map[string]any, creating bool) (map[string]any, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, err
	}
	meta, ok := result["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		result["meta"] = meta
	}
	sessions, ok := result["sessions"].([]any)
	if !ok {
		sessions = []any{}
		result["sessions"] = sessions
	}
	if _, ok := result["phases"].([]any); !ok {
		result["phases"] = []any{}
	}
	resolved, unresolved, maxes := map[string]bool{}, map[string]bool{}, map[string]bool{}
	byWeek := map[int]map[string]bool{}
	maxWeek := 0
	for _, value := range sessions {
		session, ok := value.(map[string]any)
		if !ok {
			continue
		}
		if _, ok := session["id"]; !ok {
			id, err := uuid()
			if err != nil {
				return nil, err
			}
			session["id"] = id
		}
		week := integer(session["week_number"], 1)
		if week < 1 {
			week = 1
		}
		session["week_number"] = week
		if week > maxWeek {
			maxWeek = week
		}
		day := text(session["day_of_week"])
		dayIndex := 0
		for index, candidate := range weekdays {
			if day == candidate {
				dayIndex = index + 1
				break
			}
		}
		if dayIndex == 0 {
			dayIndex = integer(session["day_index"], 1)
			if dayIndex < 1 {
				dayIndex = 1
			}
			if dayIndex > 7 {
				dayIndex = 7
			}
			session["day_of_week"] = weekdays[dayIndex-1]
		}
		session["day_index"] = dayIndex
		setDefault(session, "label", fmt.Sprintf("W%dD%d", week, dayIndex))
		if byWeek[week] == nil {
			byWeek[week] = map[string]bool{}
		}
		byWeek[week][strconv.Itoa(dayIndex)] = true
		exercises, ok := session["exercises"].([]any)
		if !ok {
			exercises = []any{}
			session["exercises"] = exercises
		}
		for _, entry := range exercises {
			exercise, ok := entry.(map[string]any)
			if !ok {
				continue
			}
			setDefault(exercise, "notes", "")
			setDefault(exercise, "sets", nil)
			setDefault(exercise, "reps", nil)
			loadType := strings.ToLower(text(exercise["load_type"]))
			switch loadType {
			case "rpe", "percentage", "absolute", "unresolvable":
			default:
				loadType = "unresolvable"
			}
			if loadType == "percentage" {
				number, err := strconv.ParseFloat(text(exercise["load_value"]), 64)
				if err != nil {
					exercise["load_value"] = nil
					loadType = "unresolvable"
				} else {
					if number > 1 {
						number /= 100
					}
					exercise["load_value"] = number
				}
			}
			exercise["load_type"] = loadType
			if id := text(exercise["glossary_id"]); id != "" {
				exercise["glossary_id"] = id
				resolved[id] = true
				if loadType == "percentage" || loadType == "rpe" {
					maxes[id] = true
				}
			} else if name := strings.TrimSpace(text(exercise["name"])); name != "" {
				unresolved[name] = true
			}
		}
	}
	days := 0
	for _, values := range byWeek {
		if len(values) > days {
			days = len(values)
		}
	}
	if creating {
		setDefault(meta, "name", "Imported Template")
		setDefault(meta, "description", "")
		setDefault(meta, "archived", false)
	}
	setDefault(meta, "estimated_weeks", maxWeek)
	setDefault(meta, "days_per_week", days)
	status := "resolved"
	if len(unresolved) > 0 {
		status = "unresolved"
		if len(resolved) > 0 {
			status = "partial"
		}
	}
	result["required_maxes"] = keys(maxes)
	result["glossary_resolution"] = map[string]any{"resolved": keys(resolved), "unresolved": keys(unresolved), "auto_added": []string{}, "resolution_status": status}
	return result, nil
}
