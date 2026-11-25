package publication

import (
	"sort"
	"strings"

	"powerlifting/export/internal/values"
)

var programFields = map[string]string{
	"phases": "program", "diet_notes": "program", "supplements": "program", "supplement_phases": "program",
	"sessions": "sessions", "competitions": "competition", "competition": "competition", "lift_profiles": "lift-profiles",
	"current_maxes": "performance", "goals": "goals", "weight_log": "weight-log", "max_history": "performance", "federation_library": "federation",
}

var metaDomains = map[string][]string{
	"competition": {"practicing_for", "weight_class_kg", "weight_class_confirm_by", "attempt_pct", "lift_attempt_settings"},
	"weight-log":  {"current_body_weight_kg", "current_body_weight_lb", "height_cm", "arm_wingspan_cm", "leg_length_cm", "body_fat_range"},
	"performance": {"target_squat_kg", "target_bench_kg", "target_dl_kg", "target_total_kg", "manual_maxes"},
	"federation":  {"federation"},
}

type Access map[string]any

func (a Access) permissions() map[string]bool {
	return stringSet(a["permissions"])
}

func stringSet(value any) map[string]bool {
	out := map[string]bool{}
	if list, ok := value.([]string); ok {
		for _, item := range list {
			out[item] = true
		}
		return out
	}
	list, _ := value.([]any)
	for _, item := range list {
		if text, ok := item.(string); ok {
			out[text] = true
		}
	}
	return out
}

func (a Access) isSelf() bool { return values.Truthy(a["is_self"]) }

func (a Access) currentBlockOnly() bool {
	return !a.isSelf() && !stringSet(a["granted_permissions"])["sessions:read"]
}

func (a Access) readScope() ([]string, bool) {
	scope, _ := a["competition_scope"].(map[string]any)
	value, present := scope["read"]
	if !present || value == nil {
		return nil, false
	}
	list, _ := value.([]any)
	out := make([]string, 0, len(list))
	for _, item := range list {
		out = append(out, values.Str(item))
	}
	return out, true
}

func entryMatches(entry map[string]any, identifiers []string) bool {
	keys := map[string]bool{}
	for _, name := range []string{"master_id", "competition_id", "id", "sk"} {
		keys[values.Str2(entry[name])] = true
	}
	for key := range keys {
		keys[strings.TrimPrefix(key, "COMP#")] = true
	}
	for _, identifier := range identifiers {
		if keys[strings.TrimPrefix(identifier, "COMP#")] {
			return true
		}
	}
	return false
}

func visibleEntries(entries []any, access Access) []any {
	identifiers, limited := access.readScope()
	if !limited {
		return entries
	}
	out := []any{}
	for _, raw := range entries {
		if entry, ok := raw.(map[string]any); ok && entryMatches(entry, identifiers) {
			out = append(out, entry)
		}
	}
	return out
}

func sessionView(session map[string]any, access Access) map[string]any {
	out := values.CopyMap(session)
	permissions := access.permissions()
	if !permissions["videos:read"] {
		delete(out, "videos")
	}
	if !permissions["weight-log:read"] {
		delete(out, "body_weight_kg")
		delete(out, "body_weight_lb")
	}
	return out
}

func inCurrentBlock(session map[string]any) bool {
	block := values.Str2(session["block"])
	if block == "" {
		block = "current"
	}
	return block == "current"
}

func ProgramView(program map[string]any, access Access) map[string]any {
	out := values.CopyMap(program)
	permissions := access.permissions()
	fields := make([]string, 0, len(programFields))
	for field := range programFields {
		fields = append(fields, field)
	}
	sort.Strings(fields)
	for _, field := range fields {
		if permissions[programFields[field]+":read"] {
			continue
		}
		if _, isList := out[field].([]any); isList {
			out[field] = []any{}
		} else {
			out[field] = map[string]any{}
		}
	}
	if sessions, ok := out["sessions"].([]any); ok {
		filtered := []any{}
		for _, raw := range sessions {
			session, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			if access.currentBlockOnly() && !inCurrentBlock(session) {
				continue
			}
			filtered = append(filtered, sessionView(session, access))
		}
		out["sessions"] = filtered
	}
	if competitions, ok := out["competitions"].([]any); ok {
		out["competitions"] = visibleEntries(competitions, access)
	}
	if !permissions["videos:read"] {
		profiles, _ := out["lift_profiles"].([]any)
		for _, raw := range profiles {
			if profile, ok := raw.(map[string]any); ok {
				delete(profile, "form_videos")
			}
		}
	}
	meta, _ := out["meta"].(map[string]any)
	if !values.Truthy(out["meta"]) {
		meta = map[string]any{}
	}
	if !permissions["program:read"] {
		names := map[string]bool{}
		for domain, fields := range metaDomains {
			if permissions[domain+":read"] {
				for _, name := range fields {
					names[name] = true
				}
			}
		}
		kept := map[string]any{}
		for name, value := range meta {
			if names[name] {
				kept[name] = value
			}
		}
		meta = kept
	}
	for domain, fields := range metaDomains {
		if !permissions[domain+":read"] {
			for _, name := range fields {
				delete(meta, name)
			}
		}
	}
	if !permissions["performance:read"] {
		blocks, _ := meta["blocks"].([]any)
		for _, raw := range blocks {
			if block, ok := raw.(map[string]any); ok {
				delete(block, "start_maxes_kg")
			}
		}
	}
	if !access.isSelf() {
		if notes, ok := meta["block_notes"].([]any); ok {
			meta["block_notes"] = sharedNotes(notes)
		}
		if notes, ok := out["block_notes"].([]any); ok {
			out["block_notes"] = sharedNotes(notes)
		}
	}
	out["meta"] = meta
	return out
}

func MarkdownView(program map[string]any, access Access) map[string]any {
	if access.isSelf() {
		return program
	}
	out := ProgramView(program, access)
	permissions := access.permissions()
	allowed := map[string]bool{"program_name": true, "blocks": true}
	for domain, fields := range metaDomains {
		if permissions[domain+":read"] {
			for _, field := range fields {
				allowed[field] = true
			}
		}
	}
	if permissions["profile:read"] {
		allowed["sex"] = true
	}
	if permissions["program:read"] {
		for _, field := range []string{"program_start", "version_label", "training_notes", "change_log", "block_notes"} {
			allowed[field] = true
		}
	}
	meta, _ := out["meta"].(map[string]any)
	filtered := map[string]any{}
	for field, value := range meta {
		if allowed[field] {
			filtered[field] = value
		}
	}
	out["meta"] = filtered
	if settings, ok := out["settings"].(map[string]any); ok {
		filteredSettings := map[string]any{}
		if sex, ok := settings["sex"]; permissions["profile:read"] && ok {
			filteredSettings["sex"] = sex
		}
		out["settings"] = filteredSettings
	}
	return out
}

func isPrivateNote(raw any) bool {
	note, ok := raw.(map[string]any)
	return ok && values.Truthy(note["private"])
}

func sharedNotes(notes []any) []any {
	shared := []any{}
	for _, raw := range notes {
		if !isPrivateNote(raw) {
			shared = append(shared, raw)
		}
	}
	return shared
}
