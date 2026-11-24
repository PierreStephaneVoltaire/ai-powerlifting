package ops

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"powerlifting/program/internal/pyval"
)

var (
	protectedMeta  = map[string]bool{"pk": true, "sk": true, "version_label": true, "updated_at": true, "published": true, "blocks": true, "current_block_id": true}
	splitPath      = regexp.MustCompile(`[.\[]`)
	sessionPath    = regexp.MustCompile(`^sessions\[(\d+)\](?:\.(.*))?$`)
	segmentPattern = regexp.MustCompile(`^(\w+)\[(\d+)\]$`)
)

func sessionLogged(session map[string]any) bool {
	switch session["status"] {
	case "logged", "completed", "skipped":
		return true
	}
	if pyval.Truthy(session["completed"]) {
		return true
	}
	exercises, _ := session["exercises"].([]any)
	for _, raw := range exercises {
		exercise, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		statuses, _ := exercise["set_statuses"].([]any)
		for _, status := range statuses {
			switch status {
			case "completed", "failed", "skipped":
				return true
			}
		}
	}
	return false
}

func validatePatches(program map[string]any, patches []any) error {
	sessions, _ := program["sessions"].([]any)
	for _, raw := range patches {
		patch, _ := raw.(map[string]any)
		path, _ := patch["path"].(string)
		parts := splitPath.Split(path, -1)
		root := parts[0]
		if protectedMeta[root] || (root == "meta" && (len(parts) == 1 || !allowedMetaFields[parts[1]] || protectedMeta[parts[1]])) {
			return validation("Protected version metadata cannot be patched: " + path)
		}
		match := sessionPath.FindStringSubmatch(path)
		if match == nil {
			continue
		}
		index, _ := strconv.Atoi(match[1])
		if index >= len(sessions) {
			return validation(fmt.Sprintf("Invalid path '%s': index %d out of range", path, index))
		}
		field := match[2]
		session, _ := sessions[index].(map[string]any)
		switch field {
		case "", "id", "session_id", "date":
			return validation("Session identity cannot be changed: " + path)
		}
		if sessionLogged(session) && (field == "exercises" || strings.HasPrefix(field, "exercises[") || field == "videos" || strings.HasPrefix(field, "videos[")) {
			return validation("Logged session data cannot be changed through new_version: " + path)
		}
	}
	return nil
}

type segment struct {
	key   string
	index int
	list  bool
}

func applyPatch(root map[string]any, path string, value any) error {
	var segments []segment
	for _, part := range strings.Split(path, ".") {
		if match := segmentPattern.FindStringSubmatch(part); match != nil {
			index, _ := strconv.Atoi(match[2])
			segments = append(segments, segment{key: match[1], index: index, list: true})
		} else {
			segments = append(segments, segment{key: part})
		}
	}
	invalid := func(format string, args ...any) error {
		return validation(fmt.Sprintf("Invalid path '%s': ", path) + fmt.Sprintf(format, args...))
	}
	var current any = root
	for _, seg := range segments[:len(segments)-1] {
		holder, isMap := current.(map[string]any)
		if seg.list {
			if !isMap {
				return invalid("'%s' not found", seg.key)
			}
			child, present := holder[seg.key]
			if !present {
				return invalid("'%s' not found", seg.key)
			}
			list, isList := child.([]any)
			if !isList {
				return invalid("'%s' is not a list", seg.key)
			}
			if seg.index >= len(list) {
				return invalid("index %d out of range", seg.index)
			}
			current = list[seg.index]
			continue
		}
		if !isMap {
			return invalid("expected dict at '%s'", seg.key)
		}
		child, present := holder[seg.key]
		if !present {
			return invalid("'%s' not found", seg.key)
		}
		current = child
	}
	last := segments[len(segments)-1]
	holder, isMap := current.(map[string]any)
	if last.list {
		if !isMap {
			return invalid("'%s' not found", last.key)
		}
		child, present := holder[last.key]
		if !present {
			return invalid("'%s' not found", last.key)
		}
		list, isList := child.([]any)
		if !isList {
			return invalid("'%s' is not a list", last.key)
		}
		if last.index >= len(list) {
			return invalid("index %d out of range", last.index)
		}
		list[last.index] = value
		return nil
	}
	if !isMap {
		return invalid("expected dict at '%s'", last.key)
	}
	holder[last.key] = value
	return nil
}

func preserveLoggedSessions(original, updated map[string]any) error {
	before, _ := original["sessions"].([]any)
	after, _ := updated["sessions"].([]any)
	for _, raw := range before {
		old, ok := raw.(map[string]any)
		if !ok || !sessionLogged(old) {
			continue
		}
		if !pyval.Truthy(old["id"]) {
			return validation("Logged sessions require a stable session id")
		}
		var match map[string]any
		for _, candidate := range after {
			if item, ok := candidate.(map[string]any); ok && pyval.Equal(item["id"], old["id"]) {
				match = item
				break
			}
		}
		if match == nil {
			return validation("Logged sessions require a stable session id")
		}
		match["id"] = old["id"]
		if sessionID, present := old["session_id"]; present {
			match["session_id"] = sessionID
		} else {
			match["session_id"] = old["id"]
		}
		for _, key := range []string{"exercises", "videos", "media_revision"} {
			if value, present := old[key]; present {
				match[key] = pyval.DeepCopy(value)
			}
		}
	}
	return nil
}

func newVersion(d *Deps, r *Request) (any, error) {
	patches, _ := r.Args["patches"].([]any)
	reason := r.Args["change_reason"]
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, "", true)
	if err != nil {
		return nil, mapError(err)
	}
	program := loaded.Program
	updated := pyval.CopyMap(program)
	if err := validatePatches(program, patches); err != nil {
		return nil, err
	}
	for _, raw := range patches {
		patch, ok := raw.(map[string]any)
		path, _ := patch["path"].(string)
		if !ok || path == "" {
			return nil, validation("Patch must have 'path' key")
		}
		if err := applyPatch(updated, path, patch["value"]); err != nil {
			return nil, err
		}
	}
	if err := preserveLoggedSessions(program, updated); err != nil {
		return nil, err
	}
	meta := metaOf(updated)
	log, _ := meta["change_log"].([]any)
	if _, present := meta["change_log"]; !present {
		log = []any{}
	}
	meta["change_log"] = append(log, map[string]any{"reason": reason, "timestamp": d.Env.Stamp()})
	written, err := d.Programs.WriteNewVersion(r.Ctx, r.Athlete, updated, false, loaded)
	if err != nil {
		return nil, mapError(err)
	}
	label := "unknown"
	if writtenMeta, ok := written.Program["meta"].(map[string]any); ok {
		if value, present := writtenMeta["version_label"]; present {
			label = pyval.Str(value)
		}
	}
	return map[string]any{"new_version": label, "change_reason": reason}, nil
}
