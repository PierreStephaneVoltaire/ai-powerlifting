package cache

import (
	"crypto/sha256"
	"fmt"
	"sort"
	"strings"

	"powerlifting/export/internal/wirejson"
)

var domains = map[string]bool{"profile": true, "program": true, "sessions": true, "competition": true, "federation": true, "glossary": true, "goals": true, "calculations": true, "performance": true, "weight-log": true, "templates": true, "imports": true, "lift-profiles": true, "analytics": true, "videos": true}

func stringList(value any) ([]string, bool) {
	switch v := value.(type) {
	case []string:
		return append([]string{}, v...), true
	case []any:
		list := make([]string, 0, len(v))
		for _, item := range v {
			text, ok := item.(string)
			if !ok {
				return nil, false
			}
			list = append(list, text)
		}
		return list, true
	default:
		return nil, false
	}
}

func Requirements(access map[string]any) map[string]any {
	permissions, _ := stringList(access["permissions"])
	filtered := []string{}
	for _, permission := range permissions {
		domain, action, ok := strings.Cut(permission, ":")
		if ok && action == "read" && domain != "analytics" && domains[domain] {
			filtered = append(filtered, permission)
		}
	}
	sort.Strings(filtered)
	scope, _ := access["competition_scope"].(map[string]any)
	competitionIDs := scope["read"]
	if list, ok := stringList(competitionIDs); ok {
		sort.Strings(list)
		competitionIDs = list
	} else if competitionIDs == nil {
		if _, present := scope["read"]; !present {
			competitionIDs = []string{}
		}
	}
	return map[string]any{"permissions": filtered, "competition_ids": competitionIDs}
}

func ScopeKey(access map[string]any) (string, error) {
	if self, ok := access["is_self"].(bool); ok && self {
		return "self", nil
	}
	payload, err := wirejson.EncodeCompact(Requirements(access))
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return fmt.Sprintf("scope#%x", sum), nil
}

func Authorize(requirements, access map[string]any) bool {
	if requirements == nil {
		self, _ := access["is_self"].(bool)
		return self
	}
	required, ok := stringList(requirements["permissions"])
	if !ok {
		return false
	}
	current, ok := stringList(access["permissions"])
	if !ok {
		return false
	}
	allowed := map[string]bool{}
	for _, v := range current {
		allowed[v] = true
	}
	for _, v := range required {
		if !allowed[v] {
			return false
		}
	}
	if allowed["competition:read"] {
		needsCompetition := false
		for _, v := range required {
			if v == "competition:read" {
				needsCompetition = true
			}
		}
		if needsCompetition {
			scope, _ := access["competition_scope"].(map[string]any)
			currentValue, present := scope["read"]
			if !present {
				currentValue = []string{}
			}
			if currentValue != nil {
				have, ok := stringList(currentValue)
				if !ok {
					return false
				}
				need, ok := stringList(requirements["competition_ids"])
				if !ok {
					return false
				}
				ids := map[string]bool{}
				for _, id := range have {
					ids[strings.TrimPrefix(id, "COMP#")] = true
				}
				for _, id := range need {
					if !ids[strings.TrimPrefix(id, "COMP#")] {
						return false
					}
				}
			}
		}
	}
	return true
}
