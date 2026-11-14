package scope

import (
	"sort"
	"time"

	"powerlifting/program/internal/pyval"
)

const (
	Active    = "current"
	AllBlocks = "all"
)

var RecordFields = []string{"diet_notes", "supplements", "supplement_phases", "competitions"}

var scopedLists = []string{"phases", "sessions", "diet_notes", "supplements", "supplement_phases", "competitions"}

var dateFields = []string{"date", "start_date", "meet_date", "competition_date", "entry_date"}

func blockID(block map[string]any) string {
	if value := pyval.Str2(block["id"]); value != "" {
		return value
	}
	return pyval.Str2(block["block_id"])
}

func BlockID(block map[string]any) string { return blockID(block) }

func ParseDate(value any) (time.Time, bool) {
	if !pyval.Truthy(value) {
		return time.Time{}, false
	}
	text := pyval.Str(value)
	if len(text) > 10 {
		text = text[:10]
	}
	parsed, err := time.Parse("2006-01-02", text)
	if err != nil || parsed.Format("2006-01-02") != text {
		return time.Time{}, false
	}
	return parsed, true
}

func blocks(program map[string]any) []map[string]any {
	meta, _ := program["meta"].(map[string]any)
	var out []map[string]any
	list, _ := meta["blocks"].([]any)
	for _, raw := range list {
		if block, ok := raw.(map[string]any); ok && blockID(block) != "" {
			out = append(out, block)
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		di, _ := ParseDate(out[i]["start_date"])
		dj, _ := ParseDate(out[j]["start_date"])
		if !di.Equal(dj) {
			return di.Before(dj)
		}
		return blockID(out[i]) < blockID(out[j])
	})
	return out
}

func CurrentBlockID(program map[string]any) string {
	meta, _ := program["meta"].(map[string]any)
	configured := pyval.Str2(meta["current_block_id"])
	if configured != "" && configured != Active {
		return configured
	}
	var active []map[string]any
	for _, block := range blocks(program) {
		if block["status"] == "active" {
			active = append(active, block)
		}
	}
	if len(active) > 0 {
		return blockID(active[len(active)-1])
	}
	if configured != "" {
		return configured
	}
	return Active
}

func Resolve(program map[string]any, id string) string {
	if id == "" || id == Active {
		return CurrentBlockID(program)
	}
	return id
}

func RecordKey(record map[string]any) string {
	if value := pyval.Str2(record["block_id"]); value != "" {
		return value
	}
	return pyval.Str2(record["block"])
}

func InBlock(record any, id, activeID string) bool {
	typed, ok := record.(map[string]any)
	if !ok {
		return false
	}
	key := RecordKey(typed)
	if id == activeID || id == Active {
		return key == activeID || key == Active
	}
	return key == id
}

func RecordDate(record map[string]any) string {
	for _, field := range dateFields {
		if value := record[field]; pyval.Truthy(value) {
			text := pyval.Str(value)
			if len(text) > 10 {
				text = text[:10]
			}
			return text
		}
	}
	return ""
}

func mostRecentCompleted(program map[string]any) string {
	var best map[string]any
	for _, block := range blocks(program) {
		if block["status"] != "completed" {
			continue
		}
		if best == nil {
			best = block
			continue
		}
		bc, cc := pyval.Str2(best["completed_at"]), pyval.Str2(block["completed_at"])
		bs, cs := pyval.Str2(best["start_date"]), pyval.Str2(block["start_date"])
		if cc > bc || (cc == bc && cs > bs) {
			best = block
		}
	}
	if best == nil {
		return ""
	}
	return blockID(best)
}

func blockForDate(day time.Time, program map[string]any) string {
	var dated []map[string]any
	for _, block := range blocks(program) {
		if _, ok := ParseDate(block["start_date"]); ok {
			dated = append(dated, block)
		}
	}
	active := CurrentBlockID(program)
	if len(dated) == 0 {
		return active
	}
	var activeStart time.Time
	hasActive := false
	for _, block := range dated {
		if blockID(block) == active {
			activeStart, _ = ParseDate(block["start_date"])
			hasActive = true
			break
		}
	}
	if hasActive && !day.Before(activeStart) {
		return active
	}
	first, _ := ParseDate(dated[0]["start_date"])
	if day.Before(first) {
		return blockID(dated[0])
	}
	for index, block := range dated {
		start, _ := ParseDate(block["start_date"])
		var next time.Time
		hasNext := index+1 < len(dated)
		if hasNext {
			next, _ = ParseDate(dated[index+1]["start_date"])
		}
		if !day.Before(start) && (!hasNext || day.Before(next)) {
			return blockID(block)
		}
	}
	return blockID(dated[len(dated)-1])
}

func RecordBlock(record any, field string, program map[string]any) string {
	active := CurrentBlockID(program)
	typed, ok := record.(map[string]any)
	if !ok {
		return active
	}
	if day, ok := ParseDate(RecordDate(typed)); ok && len(blocks(program)) > 0 {
		return blockForDate(day, program)
	}
	if stamped := RecordKey(typed); stamped != "" {
		if stamped == Active {
			return active
		}
		return stamped
	}
	if field == "supplement_phases" {
		if recent := mostRecentCompleted(program); recent != "" {
			return recent
		}
	}
	return active
}

func Entries(entries any, id string, program map[string]any, field string) []any {
	target := Resolve(program, id)
	list, _ := entries.([]any)
	out := []any{}
	for _, entry := range list {
		if typed, ok := entry.(map[string]any); ok && RecordBlock(typed, field, program) == target {
			out = append(out, typed)
		}
	}
	return out
}

func Program(program map[string]any, id string) map[string]any {
	target := Resolve(program, id)
	scoped := make(map[string]any, len(program))
	for key, value := range program {
		scoped[key] = value
	}
	for _, field := range scopedLists {
		if _, ok := program[field].([]any); ok {
			scoped[field] = Entries(program[field], target, program, field)
		}
	}
	if meta, ok := program["meta"].(map[string]any); ok {
		if _, ok := meta["block_notes"].([]any); ok {
			copied := make(map[string]any, len(meta))
			for key, value := range meta {
				copied[key] = value
			}
			copied["block_notes"] = Entries(meta["block_notes"], target, program, "meta.block_notes")
			scoped["meta"] = copied
		}
	}
	if _, ok := program["block_notes"].([]any); ok {
		scoped["block_notes"] = Entries(program["block_notes"], target, program, "block_notes")
	}
	if _, ok := program["weight_log"].([]any); ok {
		scoped["weight_log"] = Entries(program["weight_log"], target, program, "weight_log")
	}
	return scoped
}

func Stamp(record map[string]any, program map[string]any, id, field string) map[string]any {
	if !pyval.Truthy(record["block_id"]) {
		if id == "" {
			id = RecordBlock(record, field, program)
		}
		record["block_id"] = id
	}
	return record
}
