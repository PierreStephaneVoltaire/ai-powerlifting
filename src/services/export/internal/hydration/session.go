package hydration

import (
	"powerlifting/export/internal/values"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

const (
	defaultBlock  = "current"
	sessionPrefix = "session#"
)

var weekPattern = regexp.MustCompile(`(?i)W(\d+)`)

func intValue(value any, fallback int) int {
	if flag, ok := value.(bool); ok {
		if flag {
			return 1
		}
		return 0
	}
	return values.Int(value, fallback)
}

func ParseWeek(session map[string]any) int {
	if parsed := intValue(session["week_number"], -1); parsed >= 0 {
		return parsed
	}
	week := session["week"]
	if text, ok := week.(string); ok {
		if match := weekPattern.FindStringSubmatch(text); match != nil {
			number, _ := strconv.Atoi(match[1])
			return number
		}
	}
	return intValue(week, 0)
}

func phaseBlock(phase map[string]any) string {
	if value := values.Str2(phase["block"]); value != "" {
		return value
	}
	return defaultBlock
}

func ResolvePhase(session map[string]any, phases []any) map[string]any {
	week := ParseWeek(session)
	block := values.Str2(session["block"])
	if block == "" {
		block = defaultBlock
	}
	for _, raw := range phases {
		phase, ok := raw.(map[string]any)
		if !ok || phaseBlock(phase) != block {
			continue
		}
		if intValue(phase["start_week"], 0) <= week && week <= intValue(phase["end_week"], 0) {
			return values.CopyMap(phase)
		}
	}
	return map[string]any{"name": "Unscheduled", "intent": "", "start_week": int64(week), "end_week": int64(week), "block": block}
}

func programVersion(programSK string) string {
	return strings.TrimPrefix(programSK, "program#")
}

func programVersionNumber(programSK string) any {
	if !strings.HasPrefix(programSK, "program#v") {
		return nil
	}
	number, err := strconv.Atoi(strings.TrimPrefix(programSK, "program#v"))
	if err != nil {
		return nil
	}
	return int64(number)
}

var internalSessionFields = []string{"pk", "sk", "entity_type", "source_pk", "source_table", "program_sk", "program_version", "program_version_number", "source_index", "same_day_ordinal", "phase_ref", "session_id"}

func PublicSession(item map[string]any, phases []any) map[string]any {
	session, _ := values.Sanitize(values.DeepCopy(item)).(map[string]any)
	if _, ok := session["session_id"]; ok {
		if _, has := session["id"]; !has {
			session["id"] = values.Str(session["session_id"])
		}
	}
	for _, key := range internalSessionFields {
		delete(session, key)
	}
	phase := ResolvePhase(session, phases)
	session["week_number"] = int64(ParseWeek(session))
	block := values.Str2(session["block"])
	if block == "" {
		block = defaultBlock
	}
	session["block"] = block
	blockID := values.Str2(session["block_id"])
	if blockID == "" {
		blockID = block
	}
	session["block_id"] = blockID
	session["phase"] = phase
	session["phase_name"] = nameOrUnscheduled(phase)
	return session
}

func nameOrUnscheduled(phase map[string]any) string {
	if name := values.Str2(phase["name"]); name != "" {
		return name
	}
	return "Unscheduled"
}

func sortKey(item map[string]any) (string, int, int, string) {
	return values.Str2(item["date"]), intValue(item["same_day_ordinal"], 0), intValue(item["source_index"], 0), values.Str2(item["sk"])
}

func sortSessionItems(items []map[string]any) {
	sort.SliceStable(items, func(i, j int) bool {
		d1, o1, s1, k1 := sortKey(items[i])
		d2, o2, s2, k2 := sortKey(items[j])
		if d1 != d2 {
			return d1 < d2
		}
		if o1 != o2 {
			return o1 < o2
		}
		if s1 != s2 {
			return s1 < s2
		}
		return k1 < k2
	})
}
