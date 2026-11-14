package service

import (
	"strings"

	"powerlifting/competition/internal/pyval"
)

func visibleResult(name string, result any, access map[string]any) any {
	if name != "health_list_competitions" || len(access) == 0 || pyval.Truthy(access["is_self"]) {
		return result
	}
	object, ok := result.(map[string]any)
	if !ok {
		return result
	}
	list, ok := object["competitions"].([]any)
	if !ok {
		return result
	}
	scope, _ := access["competition_scope"].(map[string]any)
	identifiers, restricted := scope["read"].([]any)
	if !restricted {
		return result
	}
	allowed := map[string]bool{}
	for _, identifier := range identifiers {
		allowed[strings.TrimPrefix(pyval.Str(identifier), "COMP#")] = true
	}
	visible := make([]any, 0, len(list))
	for _, entry := range list {
		if matches(entry.(map[string]any), allowed) {
			visible = append(visible, entry)
		}
	}
	filtered := make(map[string]any, len(object))
	for key, value := range object {
		filtered[key] = value
	}
	filtered["competitions"] = visible
	return filtered
}

func matches(entry map[string]any, allowed map[string]bool) bool {
	for _, field := range []string{"master_id", "competition_id", "id", "sk"} {
		key := ""
		if pyval.Truthy(entry[field]) {
			key = pyval.Str(entry[field])
		}
		if allowed[key] || allowed[strings.TrimPrefix(key, "COMP#")] {
			return true
		}
	}
	return false
}
