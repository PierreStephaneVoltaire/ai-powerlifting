package auth

import (
	"powerlifting/analytics-export/internal/apperr"
	"powerlifting/analytics-export/internal/contract"
)

func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case float64:
		return typed != 0
	case string:
		return typed != ""
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	}
	return true
}

func conflicts(arguments map[string]any, key, expected string) bool {
	value, present := arguments[key]
	if !present || !truthy(value) {
		return false
	}
	text, isString := value.(string)
	return !isString || text != expected
}

func Scope(operation *contract.Operation, arguments map[string]any, caller Caller, access map[string]any) (map[string]any, error) {
	if !operation.Public && caller.Athlete == "" {
		return nil, apperr.Forbidden("Athlete scope required")
	}
	scoped := make(map[string]any, len(arguments)+1)
	for key, value := range arguments {
		scoped[key] = value
	}
	if conflicts(scoped, "actor_pk", caller.Person) {
		return nil, apperr.Forbidden("Acting Person differs from authenticated identity")
	}
	if _, present := scoped["actor_pk"]; present {
		scoped["actor_pk"] = caller.Person
	}
	settingsPk, _ := access["settings_pk"].(string)
	if conflicts(scoped, "viewer_username", settingsPk) {
		return nil, apperr.Forbidden("Viewer differs from authenticated Person")
	}
	if operation.HasInput("viewer_username") {
		if settingsPk == "" {
			delete(scoped, "viewer_username")
		} else {
			scoped["viewer_username"] = settingsPk
		}
	}
	for _, key := range []string{"pk", "user_pk", "mapped_pk", "_user_pk"} {
		if conflicts(scoped, key, caller.Athlete) {
			return nil, apperr.Forbidden("Operation ownership conflicts with authenticated scope")
		}
	}
	if !operation.Public {
		scoped["pk"] = caller.Athlete
	}
	return scoped, nil
}
