package access

import (
	"context"
	"slices"
	"strings"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var metaDomains = []struct {
	Domain string
	Fields []string
}{
	{"competition", []string{"practicing_for", "weight_class_kg", "weight_class_confirm_by", "attempt_pct", "lift_attempt_settings"}},
	{"weight-log", []string{"current_body_weight_kg", "current_body_weight_lb", "height_cm", "arm_wingspan_cm", "leg_length_cm", "body_fat_range"}},
	{"performance", []string{"target_squat_kg", "target_bench_kg", "target_dl_kg", "target_total_kg", "manual_maxes"}},
	{"federation", []string{"federation"}},
}

type Checker struct {
	Rules   func(string) (contract.Rule, bool)
	DB      *store.DB
	Backend func(source string) bool
}

type Claims struct {
	Athlete string
	Source  string
}

func truthyBool(arguments map[string]any, key string) bool { return arguments[key] == true }

func OperationPermission(rules func(string) (contract.Rule, bool), name string, arguments map[string]any) string {
	switch name {
	case "health_list_competitions":
		operation, _ := arguments["op"].(string)
		if !value.Truthy(arguments["op"]) {
			operation = "list"
			if value.Truthy(arguments["master_id"]) && arguments["patch"] != nil {
				operation = "update"
			} else if value.Truthy(arguments["master_id"]) && arguments["results"] != nil {
				operation = "complete"
			}
		}
		switch operation {
		case "list":
			return "competition:read"
		case "update", "complete":
			return "competition:write"
		}
		return ""
	case "domain_resume":
		resumed, _ := arguments["operation"].(string)
		if resumed == "domain_resume" || resumed == "generation_status" {
			return ""
		}
		return OperationPermission(rules, resumed, map[string]any{})
	}
	rule, ok := rules(name)
	if !ok || rule.Permission == "" {
		return ""
	}
	if (name == "analytics.blocks_get" || truthyBool(arguments, "cache_only") || truthyBool(arguments, "cacheOnly")) && !truthyBool(arguments, "refresh") {
		if rule.CacheRead != "" {
			return rule.CacheRead
		}
	}
	return rule.Permission
}

func (c *Checker) Check(ctx context.Context, operation string, arguments map[string]any, claims Claims, access *Context) error {
	rule, ok := c.Rules(operation)
	if !ok {
		return apperr.Forbidden("Operation has no permission mapping")
	}
	if rule.InternalOnly && !c.Backend(claims.Source) {
		return apperr.Forbidden("Operation is internal to the gateway")
	}
	if operation == "identity_resolve" || operation == "access_context" || rule.Public {
		return nil
	}
	permission := OperationPermission(c.Rules, operation, arguments)
	if !access.Has(permission) {
		return apperr.Forbidden("Not permitted")
	}
	if requirements, present := arguments["_required_access"]; present {
		if err := authorizeSource(requirements, access); err != nil {
			return err
		}
	}
	if err := authorizeEntry(operation, arguments, permission, access); err != nil {
		return err
	}
	if err := authorizeProgramChange(operation, arguments, access); err != nil {
		return err
	}
	media, err := c.mediaPermission(ctx, operation, arguments, claims.Athlete)
	if err != nil {
		return err
	}
	if media != "" && !access.Has(media) {
		return apperr.Forbidden(media + " permission required")
	}
	return nil
}

func stripComp(id string) string { return strings.TrimPrefix(id, "COMP#") }

func authorizeSource(requirements any, access *Context) error {
	if requirements == nil {
		if access.IsSelf {
			return nil
		}
		return apperr.Forbidden("This saved result needs to be regenerated with current access")
	}
	object, _ := requirements.(map[string]any)
	required, _ := object["permissions"].([]any)
	var names []string
	for _, entry := range required {
		names = append(names, value.Str(entry))
	}
	for _, name := range names {
		if !slices.Contains(access.Permissions, name) {
			return apperr.Forbidden("Access to this saved result has changed")
		}
	}
	if slices.Contains(names, "competition:read") && !access.ReadScope.Unrestricted {
		ids, listed := object["competition_ids"].([]any)
		if !listed {
			return apperr.Forbidden("This saved result includes Competition Entries outside the current grant")
		}
		for _, id := range ids {
			if !slices.ContainsFunc(access.ReadScope.IDs, func(have string) bool { return stripComp(have) == stripComp(value.Str(id)) }) {
				return apperr.Forbidden("This saved result includes Competition Entries outside the current grant")
			}
		}
	}
	return nil
}

func EntryMatches(entry map[string]any, scope Scope) bool {
	keys := map[string]bool{}
	for _, field := range []string{"master_id", "competition_id", "id", "sk"} {
		if value.Truthy(entry[field]) {
			keys[value.Str(entry[field])] = true
		} else {
			keys[""] = true
		}
	}
	for key := range keys {
		keys[stripComp(key)] = true
	}
	for _, identifier := range scope.IDs {
		if keys[stripComp(identifier)] {
			return true
		}
	}
	return false
}

func authorizeEntry(operation string, arguments map[string]any, permission string, access *Context) error {
	if !strings.HasPrefix(operation, "health_") || !strings.Contains(operation, "competition") {
		return nil
	}
	action := "read"
	if permission == "competition:write" {
		action = "write"
	}
	scope := access.ReadScope
	if action == "write" {
		scope = access.WriteScope
	}
	if scope.Unrestricted || (operation == "health_list_competitions" && action == "read") {
		return nil
	}
	target := arguments
	if entry, ok := arguments["competition"].(map[string]any); ok && len(entry) > 0 {
		target = entry
	}
	if !EntryMatches(target, scope) {
		return apperr.Forbidden("This Competition Entry is outside the current grant")
	}
	return nil
}

func authorizeProgramChange(operation string, arguments map[string]any, access *Context) error {
	required := map[string]bool{}
	fields := map[string]bool{}
	switch {
	case operation == "program_update_meta_field":
		if updates, ok := arguments["updates"].(map[string]any); ok {
			for field := range updates {
				fields[field] = true
			}
		} else {
			fields[value.Str(arguments["field"])] = true
		}
	case operation == "template_apply" || operation == "template_apply_confirm":
		for _, permission := range []string{"program:read", "performance:read", "glossary:read"} {
			if !access.Has(permission) {
				return apperr.Forbidden(permission + " permission required")
			}
		}
		if operation == "template_apply_confirm" {
			required["program"], required["sessions"] = true, true
			target, given := arguments["target"]
			if !given || target == "new_block" {
				required["performance"] = true
			}
		}
	case operation == "block_transition" && arguments["action"] != "rename":
		required["sessions"] = true
		if arguments["action"] == "start_next" || arguments["action"] == "complete_and_start" {
			required["performance"] = true
		}
	case operation == "health_setup_initialize":
		required["sessions"], required["performance"] = true, true
		if arguments["mode"] == "template" && !access.Has("templates:read") {
			return apperr.Forbidden("templates:read permission required")
		}
	}
	for _, group := range metaDomains {
		for _, name := range group.Fields {
			if fields[name] {
				required[group.Domain] = true
			}
		}
	}
	domains := make([]string, 0, len(required))
	for domain := range required {
		domains = append(domains, domain)
	}
	slices.Sort(domains)
	for _, domain := range domains {
		if !access.Has(domain + ":write") {
			return apperr.Forbidden(domain + ":write permission required")
		}
	}
	if required["competition"] && !access.WriteScope.Unrestricted {
		return apperr.Forbidden("Edit tied Competition Entries through their individual operations")
	}
	return nil
}

func (c *Checker) mediaPermission(ctx context.Context, operation string, arguments map[string]any, athlete string) (string, error) {
	if operation == "video_upload_presign" {
		if value.Truthy(arguments["lift"]) {
			return "lift-profiles:write", nil
		}
		return "", nil
	}
	switch operation {
	case "video_upload_confirm", "video_media_resolve", "video_remove", "video_update_metadata":
	default:
		return "", nil
	}
	identifiers := []string{textOf(arguments["video_id"])}
	if operation == "video_media_resolve" {
		parts := strings.Split(textOf(arguments["s3_key"]), "/")
		last := parts[len(parts)-1]
		if dot := strings.LastIndex(last, "."); dot >= 0 {
			last = last[:dot]
		}
		parent := ""
		if len(parts) > 1 {
			parent = parts[len(parts)-2]
		}
		identifiers = []string{last, parent}
	}
	for _, identifier := range identifiers {
		if identifier == "" {
			continue
		}
		media, err := c.DB.Get(ctx, c.DB.Tables.Videos, store.Key{"athlete_id": athlete, "video_id": identifier})
		if err != nil {
			return "", err
		}
		if media == nil {
			continue
		}
		if value.Str(value.Or(media["media_id"], value.Or(media["video_id"], ""))) != identifier {
			continue
		}
		if value.Truthy(media["lift"]) {
			if operation == "video_media_resolve" {
				return "lift-profiles:read", nil
			}
			return "lift-profiles:write", nil
		}
		return "", nil
	}
	return "", apperr.Forbidden("Media allocation is unavailable for this Athlete")
}

func textOf(v any) string {
	if !value.Truthy(v) {
		return ""
	}
	return value.Str(v)
}
