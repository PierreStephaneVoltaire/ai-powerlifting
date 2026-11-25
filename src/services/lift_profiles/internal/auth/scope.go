package auth

import (
	"maps"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/contract"
)

var Reserved = []string{"_person_pk", "_access", "_if_job_id"}

func conflicts(arguments map[string]any, key, expected string) bool {
	text, isText := arguments[key].(string)
	if !isText {
		return arguments[key] != nil
	}
	return text != "" && text != expected
}

func Scope(operation *contract.Operation, arguments map[string]any, caller Caller) (map[string]any, error) {
	if caller.Athlete == "" {
		return nil, apperr.Forbidden("Athlete scope required")
	}
	scoped := maps.Clone(arguments)
	if scoped == nil {
		scoped = map[string]any{}
	}
	for _, key := range []string{"pk", "user_pk", "mapped_pk", "_user_pk"} {
		if conflicts(scoped, key, caller.Athlete) {
			return nil, apperr.Forbidden("Operation ownership conflicts with authenticated scope")
		}
	}
	scoped["pk"] = caller.Athlete
	return scoped, nil
}
