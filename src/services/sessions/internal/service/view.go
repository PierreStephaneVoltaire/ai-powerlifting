package service

import (
	"powerlifting/sessions/internal/value"
)

func permissionSet(access map[string]any, key string) map[string]bool {
	set := map[string]bool{}
	list, _ := access[key].([]any)
	for _, entry := range list {
		if name, ok := entry.(string); ok {
			set[name] = true
		}
	}
	return set
}

func isSelf(access map[string]any) bool { return value.Truthy(access["is_self"]) }

func sessionView(session map[string]any, access map[string]any) map[string]any {
	out := value.Copy(session).(map[string]any)
	permissions := permissionSet(access, "permissions")
	if !permissions["videos:read"] {
		delete(out, "videos")
	}
	if !permissions["weight-log:read"] {
		delete(out, "body_weight_kg")
		delete(out, "body_weight_lb")
	}
	return out
}

func currentBlockOnly(access map[string]any) bool {
	return !isSelf(access) && !permissionSet(access, "granted_permissions")["sessions:read"]
}

func inCurrentBlock(session map[string]any) bool {
	return value.Or(session["block"], "current") == "current"
}

func visibleSessions(items []any, access map[string]any) []any {
	filter := currentBlockOnly(access)
	out := make([]any, 0, len(items))
	for _, entry := range items {
		session, ok := entry.(map[string]any)
		if !ok {
			continue
		}
		if filter && !inCurrentBlock(session) {
			continue
		}
		out = append(out, sessionView(session, access))
	}
	return out
}

func operationResult(name string, result any, access map[string]any) any {
	if isSelf(access) {
		return result
	}
	switch name {
	case "session_get":
		if session, ok := result.(map[string]any); ok {
			return sessionView(session, access)
		}
	case "session_list", "session_list_full", "health_get_sessions_range":
		switch typed := result.(type) {
		case []any:
			return visibleSessions(typed, access)
		case map[string]any:
			sessions, _ := typed["sessions"].([]any)
			out := make(map[string]any, len(typed))
			for key, v := range typed {
				out[key] = v
			}
			out["sessions"] = visibleSessions(sessions, access)
			return out
		}
	}
	return result
}
