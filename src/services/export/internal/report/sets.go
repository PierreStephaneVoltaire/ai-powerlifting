package report

import (
	"fmt"
	"powerlifting/export/internal/values"
)

var perSetFields = map[string]bool{"sets_data": true, "set_ids": true, "set_statuses": true, "failed_set_reasons": true}

func valueKey(value any) string {
	if values.IsNumber(value) {
		number, _ := values.Float(value)
		return fmt.Sprintf("n:%v", number)
	}
	return fmt.Sprintf("%T:%s", value, values.Str(value))
}

func at(values any, index int) any {
	list, ok := values.([]any)
	if ok && index < len(list) {
		return list[index]
	}
	return nil
}

func expandPerformedSets(exercise map[string]any) []map[string]any {
	setsData, ok := exercise["sets_data"].([]any)
	hasDict := false
	for _, item := range setsData {
		if _, isMap := item.(map[string]any); isMap {
			hasDict = true
		}
	}
	if !ok || !hasDict {
		return []map[string]any{exercise}
	}
	type triple struct{ reps, kg, rpe any }
	performed := make([]triple, len(setsData))
	statuses := make([]any, len(setsData))
	reasons := make([]any, len(setsData))
	failures := false
	uniqueValues, uniqueStatuses := map[string]bool{}, map[string]bool{}
	for index, raw := range setsData {
		item, _ := raw.(map[string]any)
		pick := func(key string) any {
			if value, present := item[key]; present {
				return value
			}
			return exercise[key]
		}
		performed[index] = triple{pick("reps"), pick("kg"), pick("rpe")}
		statuses[index] = at(exercise["set_statuses"], index)
		if statuses[index] == "failed" {
			failures = true
		}
		reasons[index] = at(exercise["failed_set_reasons"], index)
		if reasons[index] == nil {
			reasons[index] = []any{}
		}
		uniqueValues[valueKey(performed[index].reps)+"|"+valueKey(performed[index].kg)+"|"+valueKey(performed[index].rpe)] = true
		uniqueStatuses[valueKey(statuses[index])] = true
	}
	if len(uniqueValues) == 1 && len(uniqueStatuses) == 1 && !failures {
		merged := values.CopyMap(exercise)
		merged["sets"] = int64(len(setsData))
		merged["reps"], merged["kg"], merged["rpe"] = performed[0].reps, performed[0].kg, performed[0].rpe
		return []map[string]any{merged}
	}
	base := map[string]any{}
	for key, value := range exercise {
		if !perSetFields[key] {
			base[key] = value
		}
	}
	rows := make([]map[string]any, 0, len(setsData))
	for index := range setsData {
		row := values.CopyMap(base)
		row["sets"] = int64(1)
		row["reps"], row["kg"], row["rpe"] = performed[index].reps, performed[index].kg, performed[index].rpe
		row["set_number"] = int64(index + 1)
		row["failed_set_reasons"] = []any{reasons[index]}
		if index == 0 {
			if notes, present := exercise["notes"]; present {
				row["notes"] = notes
			} else {
				row["notes"] = ""
			}
		} else {
			row["notes"] = ""
		}
		if statuses[index] != nil {
			row["set_statuses"] = []any{statuses[index]}
		}
		if values.Truthy(exercise["id"]) {
			row["id"] = fmt.Sprintf("%s-set%d", values.Str(exercise["id"]), index+1)
		}
		rows = append(rows, row)
	}
	return rows
}

func ExpandSessionSets(sessions []any) []any {
	out := make([]any, 0, len(sessions))
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			out = append(out, raw)
			continue
		}
		if exercises, isList := session["exercises"].([]any); isList {
			copied := make(map[string]any, len(session))
			for key, value := range session {
				copied[key] = value
			}
			expanded := []any{}
			for _, item := range exercises {
				if exercise, isMap := item.(map[string]any); isMap {
					for _, row := range expandPerformedSets(exercise) {
						expanded = append(expanded, row)
					}
				}
			}
			copied["exercises"] = expanded
			session = copied
		}
		out = append(out, session)
	}
	return out
}
