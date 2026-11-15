package auth

import (
	"slices"
	"strings"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/value"
)

type Who struct {
	SettingsPK   string
	OwnAthletePK string
	Operator     bool
}

func truthy(v any) bool { return value.Truthy(v) }

func conflicts(arguments map[string]any, key, expected string) bool {
	given, present := arguments[key]
	if !present || !truthy(given) {
		return false
	}
	text, isString := given.(string)
	return !isString || text != expected
}

var identitySelectors = []string{"identity_provider", "identity_sub", "identity_issuer", "discord_id", "authentik_sub"}

func Scope(operation *contract.Operation, arguments map[string]any, caller Caller, who Who) (map[string]any, error) {
	if operation.Name == "identity_resolve" {
		return clone(arguments), nil
	}
	if !operation.Public && caller.Athlete == "" {
		return nil, apperr.Forbidden("Athlete scope required")
	}
	if operation.Ownership == "operator" && !who.Operator {
		return nil, apperr.Forbidden("Operator permission required")
	}
	scoped := clone(arguments)
	if conflicts(scoped, "actor_pk", caller.Person) {
		return nil, apperr.Forbidden("Acting Person differs from authenticated identity")
	}
	if _, present := scoped["actor_pk"]; present {
		scoped["actor_pk"] = caller.Person
	}
	if conflicts(scoped, "viewer_username", who.SettingsPK) {
		return nil, apperr.Forbidden("Viewer differs from authenticated Person")
	}
	if operation.HasInput("viewer_username") {
		if who.SettingsPK == "" {
			delete(scoped, "viewer_username")
		} else {
			scoped["viewer_username"] = who.SettingsPK
		}
	}
	isGrant := strings.HasPrefix(operation.Name, "grant_")
	if operation.Ownership == "person" && !isGrant {
		if caller.Person == "" || who.SettingsPK == "" {
			return nil, apperr.Forbidden("Authenticated Person required")
		}
		for _, key := range identitySelectors {
			if truthy(scoped[key]) {
				return nil, apperr.Forbidden("Identity selectors are not settings selectors")
			}
		}
		allowed := []string{who.SettingsPK, caller.Person, who.OwnAthletePK}
		for _, key := range []string{"username", "discord_username", "mapped_pk", "pk"} {
			given := scoped[key]
			if !truthy(given) {
				continue
			}
			text, isString := given.(string)
			if !isString || !slices.Contains(allowed, text) {
				return nil, apperr.Forbidden("Person selector conflicts with authenticated identity")
			}
		}
		if operation.HasInput("username") {
			scoped["username"] = who.SettingsPK
		}
		if _, present := scoped["mapped_pk"]; present {
			scoped["mapped_pk"] = who.OwnAthletePK
		}
		scoped["pk"] = who.SettingsPK
		return scoped, nil
	}
	if isGrant {
		if caller.Person == "" {
			return nil, apperr.Forbidden("Person scope required")
		}
		target, _ := arguments["athlete_mapped_pk"].(string)
		if target != "" && target != caller.Athlete {
			return nil, apperr.Forbidden("Grant target differs from authenticated Athlete")
		}
		if operation.Name == "grant_check" && arguments["actor_mapped_pk"] != caller.Person {
			return nil, apperr.Forbidden("Grant check actor differs from authenticated Person")
		}
		if operation.Name == "grant_list" && target == "" && arguments["grantee_mapped_pk"] != caller.Person {
			return nil, apperr.Forbidden("Grants may only be listed for the authenticated Person")
		}
		switch operation.Name {
		case "grant_create":
			scoped["created_by"] = caller.Person
		case "grant_revoke":
			scoped["revoked_by"] = caller.Person
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

func clone(arguments map[string]any) map[string]any {
	out := make(map[string]any, len(arguments)+1)
	for key, v := range arguments {
		out[key] = v
	}
	return out
}
