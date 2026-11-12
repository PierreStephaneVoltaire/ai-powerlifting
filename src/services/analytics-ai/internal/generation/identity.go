package generation

import (
	"crypto/sha256"
	"encoding/hex"
	"slices"
	"strings"

	"powerlifting/analytics-ai/internal/pyjson"
)

var readableDomains = []string{"profile", "program", "sessions", "competition", "federation", "glossary", "goals", "budget", "calculations", "performance", "weight-log", "templates", "imports", "lift-profiles", "analytics", "videos"}

func Fingerprint(operation string, arguments map[string]any, identity map[string]any) (string, error) {
	inputs := map[string]any{}
	for key, value := range arguments {
		if strings.HasPrefix(key, "_") || key == "refresh" || key == "cache_only" {
			continue
		}
		inputs[key] = value
	}
	var source any
	if identity != nil {
		source = identity
	}
	encoded, err := pyjson.Encode(map[string]any{"operation": operation, "inputs": inputs, "source": source})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func ReadRequirements(access map[string]any) map[string]any {
	permissions := []any{}
	granted, _ := access["permissions"].([]any)
	names := []string{}
	for _, entry := range granted {
		name, _ := entry.(string)
		domain, action, found := strings.Cut(name, ":")
		if found && action == "read" && slices.Contains(readableDomains, domain) {
			names = append(names, name)
		}
	}
	slices.Sort(names)
	for _, name := range names {
		permissions = append(permissions, name)
	}
	var competitions any = []any{}
	if scope, ok := access["competition_scope"].(map[string]any); ok {
		if read, present := scope["read"]; present {
			competitions = read
		}
	}
	return map[string]any{"permissions": permissions, "competition_ids": competitions}
}

func AuthorizeSource(requirements map[string]any, access map[string]any) error {
	if requirements == nil {
		if self, _ := access["is_self"].(bool); self {
			return nil
		}
		return ErrRegenerate
	}
	granted := stringSet(access["permissions"])
	required := stringList(requirements["permissions"])
	for _, permission := range required {
		if !granted[permission] {
			return ErrAccessChanged
		}
	}
	if !slices.Contains(required, "competition:read") {
		return nil
	}
	scope, _ := access["competition_scope"].(map[string]any)
	raw, declared := scope["read"]
	if declared && raw == nil {
		return nil
	}
	current, _ := raw.([]any)
	have := map[string]bool{}
	for _, value := range current {
		text, _ := value.(string)
		have[strings.TrimPrefix(text, "COMP#")] = true
	}
	ids, ok := requirements["competition_ids"].([]any)
	if !ok {
		return ErrOutsideGrant
	}
	for _, value := range ids {
		text, _ := value.(string)
		if !have[strings.TrimPrefix(text, "COMP#")] {
			return ErrOutsideGrant
		}
	}
	return nil
}

func stringSet(value any) map[string]bool {
	set := map[string]bool{}
	for _, text := range stringList(value) {
		set[text] = true
	}
	return set
}

func stringList(value any) []string {
	items, _ := value.([]any)
	out := make([]string, 0, len(items))
	for _, item := range items {
		if text, ok := item.(string); ok {
			out = append(out, text)
		}
	}
	return out
}
