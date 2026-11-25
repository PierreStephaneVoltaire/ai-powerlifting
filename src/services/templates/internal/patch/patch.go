package patch

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"powerlifting/templates/internal/payload"
	"powerlifting/templates/internal/wirejson"
)

var fields = []string{"sets", "reps", "rep_unit", "rep_mode", "load_type", "load_value", "rpe_target", "notes"}
var weekdays = []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}

func stringValue(v any) string { value, _ := v.(string); return value }

func normalName(name string) string {
	var out strings.Builder
	invalid := false
	for _, r := range strings.ToLower(name) {
		if r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == ' ' {
			out.WriteRune(r)
			invalid = false
		} else if !invalid {
			out.WriteByte(' ')
			invalid = true
		}
	}
	return strings.TrimSpace(out.String())
}

func tokens(name string) string {
	parts := strings.FieldsFunc(strings.ToLower(name), unicode.IsSpace)
	sort.Strings(parts)
	return strings.Join(parts, " ")
}

func similarity(a, b string) float64 {
	x, y := []rune(tokens(a)), []rune(tokens(b))
	if len(x)+len(y) == 0 {
		return 1
	}
	previous := make([]int, len(y)+1)
	for _, r := range x {
		next := make([]int, len(y)+1)
		for j, other := range y {
			if r == other {
				next[j+1] = previous[j] + 1
			} else {
				next[j+1] = max(previous[j+1], next[j])
			}
		}
		previous = next
	}
	return 2 * float64(previous[len(y)]) / float64(len(x)+len(y))
}

func resolver(glossary []map[string]any) func(string) map[string]any {
	cache := map[string]map[string]any{}
	return func(name string) map[string]any {
		if item, ok := cache[name]; ok {
			return item
		}
		best := 0.0
		var result map[string]any
		for _, entry := range glossary {
			score := similarity(name, stringValue(entry["name"]))
			if score > best {
				best, result = score, entry
			}
		}
		if best < 0.92 {
			result = nil
		}
		cache[name] = result
		return result
	}
}

func snapshot(ex map[string]any) map[string]any {
	out := map[string]any{}
	for _, key := range append([]string{"name"}, fields...) {
		if ex[key] != nil {
			out[key] = ex[key]
		}
	}
	return out
}

func inScope(session, op map[string]any) bool {
	weeks, _ := op["weeks"].([]any)
	if len(weeks) > 0 {
		found := false
		for _, week := range weeks {
			if fmt.Sprint(week) == fmt.Sprint(session["week_number"]) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	days, _ := op["days"].([]any)
	if len(days) == 0 && stringValue(op["day_of_week"]) != "" {
		days = []any{op["day_of_week"]}
	}
	if len(days) > 0 {
		for _, day := range days {
			if strings.EqualFold(stringValue(day), stringValue(session["day_of_week"])) {
				return true
			}
		}
		return false
	}
	return true
}

func rename(ex map[string]any, name string, resolve func(string) map[string]any) {
	entry := resolve(name)
	ex["name"] = name
	if resolved := stringValue(entry["name"]); resolved != "" {
		ex["name"] = resolved
	}
	if id := stringValue(entry["id"]); id != "" {
		ex["glossary_id"] = id
	} else {
		delete(ex, "glossary_id")
	}
}

func prescribe(ex, op map[string]any) error {
	if err := payload.NormalizePrescription(ex); err != nil {
		return err
	}
	changes := map[string]any{}
	for _, key := range fields {
		if v, ok := op[key]; ok {
			changes[key] = v
		}
	}
	if changes["rep_mode"] == "amrap" {
		if _, ok := changes["reps"]; !ok {
			changes["reps"] = nil
		}
		if _, ok := changes["rep_unit"]; !ok {
			changes["rep_unit"] = "reps"
		}
	} else if changes["rep_unit"] == "minutes" || changes["rep_unit"] == "seconds" || changes["reps"] != nil {
		if _, ok := changes["rep_mode"]; !ok {
			changes["rep_mode"] = nil
		}
	}
	if changes["rep_unit"] == "reps" && ex["load_type"] == "duration" {
		if _, ok := changes["load_type"]; !ok {
			changes["load_type"] = "unresolvable"
		}
	}
	for key, value := range changes {
		ex[key] = value
	}
	return payload.NormalizePrescription(ex)
}

func Apply(template map[string]any, operations []any, glossary []map[string]any) (map[string]any, []any, []any, error) {
	patched, err := payload.Clone(template)
	if err != nil {
		return nil, nil, nil, err
	}
	sessions, _ := patched["sessions"].([]any)
	changes, unmatched := []any{}, []any{}
	resolve := resolver(glossary)
	for index, raw := range operations {
		op, _ := raw.(map[string]any)
		kind := stringValue(op["op"])
		if kind == "set_session_weekdays" {
			positions, _ := op["weekdays"].(map[string]any)
			keys := make([]string, 0, len(positions))
			for key := range positions {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for _, key := range keys {
				position, err := strconv.Atoi(key)
				if err != nil || position < 1 || position > len(sessions) {
					return nil, nil, nil, fmt.Errorf("Session %s does not exist in this template", key)
				}
				session, _ := sessions[position-1].(map[string]any)
				day := stringValue(positions[key])
				weekday := -1
				for i, name := range weekdays {
					if name == day {
						weekday = i
						break
					}
				}
				if session == nil || weekday < 0 {
					return nil, nil, nil, fmt.Errorf("invalid session weekday")
				}
				before := map[string]any{"day_of_week": session["day_of_week"], "day_index": session["day_index"]}
				after := map[string]any{"day_of_week": day, "day_index": weekday + 1}
				positionValue, err := strconv.ParseFloat(fmt.Sprint(before["day_index"]), 64)
				if before["day_of_week"] != day || err != nil || positionValue != float64(weekday+1) {
					session["day_of_week"], session["day_index"] = day, weekday+1
					changes = append(changes, map[string]any{"op": index, "session_position": position, "week": session["week_number"], "day": day, "before": before, "after": after})
				}
			}
			continue
		}
		touched := 0
		for _, rawSession := range sessions {
			session, ok := rawSession.(map[string]any)
			if !ok || !inScope(session, op) {
				continue
			}
			where := map[string]any{"op": index, "week": session["week_number"], "day": session["day_of_week"]}
			exercises, _ := session["exercises"].([]any)
			if exercises == nil {
				exercises = []any{}
			}
			if kind == "add_exercise" {
				added := map[string]any{"name": op["name"]}
				for _, key := range fields {
					if v, ok := op[key]; ok {
						added[key] = v
					}
				}
				rename(added, stringValue(op["name"]), resolve)
				if err := payload.NormalizePrescription(added); err != nil {
					return nil, nil, nil, err
				}
				exercises = append(exercises, added)
				where["before"], where["after"] = nil, snapshot(added)
				changes = append(changes, where)
				touched++
			} else {
				target := stringValue(op["exercise"])
				if kind == "replace_exercise" {
					target = stringValue(op["from"])
				}
				updated := make([]any, 0, len(exercises))
				for _, item := range exercises {
					ex, ok := item.(map[string]any)
					if !ok {
						updated = append(updated, item)
						continue
					}
					entry := resolve(target)
					if normalName(stringValue(ex["name"])) != normalName(target) && !(stringValue(ex["glossary_id"]) != "" && stringValue(ex["glossary_id"]) == stringValue(entry["id"])) {
						updated = append(updated, item)
						continue
					}
					before := snapshot(ex)
					switch kind {
					case "replace_exercise":
						rename(ex, stringValue(op["to"]), resolve)
					case "set_prescription":
						if err := prescribe(ex, op); err != nil {
							return nil, nil, nil, err
						}
					case "remove_exercise":
					default:
						updated = append(updated, item)
						continue
					}
					change := map[string]any{"op": index, "week": session["week_number"], "day": session["day_of_week"], "before": before, "after": nil}
					if kind != "remove_exercise" {
						change["after"] = snapshot(ex)
						updated = append(updated, item)
					}
					changes = append(changes, change)
					touched++
				}
				exercises = updated
			}
			session["exercises"] = exercises
		}
		if touched == 0 {
			unmatched = append(unmatched, map[string]any{"op": index, "operation": op})
		}
	}
	return patched, changes, unmatched, nil
}

func Hash(sk string, operations []any) (string, error) {
	raw, err := wirejson.Encode(map[string]any{"sk": sk, "operations": operations})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), nil
}
