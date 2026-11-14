package ops

import (
	"math"
	"regexp"
	"strings"
	"time"

	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

var (
	nonAlnum = regexp.MustCompile(`[^a-z0-9]+`)
	weekdays = map[string]bool{"Monday": true, "Tuesday": true, "Wednesday": true, "Thursday": true, "Friday": true, "Saturday": true, "Sunday": true}
	weekText = regexp.MustCompile(`(?i)W(\d+)`)
)

func reservedName(value any) bool {
	name, ok := value.(string)
	if !ok {
		return false
	}
	spaced := strings.TrimSpace(nonAlnum.ReplaceAllString(strings.ToLower(name), " "))
	return spaced == "current" || spaced == "current block"
}

func isoDate(text string) bool {
	for _, layout := range []string{"2006-01-02", "20060102"} {
		if parsed, err := time.Parse(layout, text); err == nil && parsed.Format(layout) == text {
			return true
		}
	}
	return false
}

func capitalize(text string) string {
	if text == "" {
		return text
	}
	return strings.ToUpper(text[:1]) + strings.ToLower(text[1:])
}

func validateTransitionStart(startDate, weekStartDay, maxes any) error {
	date, ok := startDate.(string)
	if !ok || date == "" {
		return validation("start_next requires start_date, week_start_day, and confirmed start_maxes_kg")
	}
	if !isoDate(date) {
		return validation("start_date must be an ISO date")
	}
	day, ok := weekStartDay.(string)
	if !ok || !weekdays[capitalize(day)] {
		return validation("week_start_day must be a weekday")
	}
	values, ok := maxes.(map[string]any)
	valid := ok && len(values) > 0
	if valid {
		for _, value := range values {
			if _, isBool := value.(bool); isBool || !pyval.IsNumber(value) {
				valid = false
				break
			}
			number, _ := pyval.Float(value)
			if number <= 0 || math.IsInf(number, 0) || math.IsNaN(number) {
				valid = false
				break
			}
		}
	}
	if !valid {
		return validation("start_maxes_kg must contain positive numeric maxes")
	}
	return nil
}

func sessionWeek(session map[string]any) int {
	if number, ok := pyval.Truncate(session["week_number"]); ok && session["week_number"] != nil && number >= 0 {
		return number
	}
	week := session["week"]
	if text, ok := week.(string); ok {
		if match := weekText.FindStringSubmatch(text); match != nil {
			number, _ := pyval.Truncate(match[1])
			return number
		}
	}
	if number, ok := pyval.Truncate(week); ok && week != nil {
		return number
	}
	return 0
}

type plan struct {
	phases   []map[string]any
	sessions []map[string]any
}

func validateNextProgram(value any) (*plan, error) {
	if value == nil {
		return &plan{}, nil
	}
	next, ok := value.(map[string]any)
	if !ok {
		return nil, validation("next_program must be an object")
	}
	phases, phasesOK := listArg(next, "phases")
	sessions, sessionsOK := listArg(next, "sessions")
	if !phasesOK || !sessionsOK {
		return nil, validation("next_program phases and sessions must be arrays")
	}
	result := &plan{}
	for _, raw := range phases {
		phase, ok := raw.(map[string]any)
		if !ok {
			return nil, validation("next_program phases must contain objects")
		}
		start := 1
		if present, has := phase["start_week"]; has {
			parsed, ok := pyval.Truncate(present)
			if !ok || present == nil {
				return nil, validation("phase week ranges must be integers")
			}
			start = parsed
		}
		end := start
		if present, has := phase["end_week"]; has {
			parsed, ok := pyval.Truncate(present)
			if !ok || present == nil {
				return nil, validation("phase week ranges must be integers")
			}
			end = parsed
		}
		if start < 1 || end < start {
			return nil, validation("phase week ranges must be positive and ordered")
		}
		normalized := pyval.CopyMap(phase)
		normalized["start_week"] = int64(start)
		normalized["end_week"] = int64(end)
		result.phases = append(result.phases, normalized)
	}
	seen := map[string]bool{}
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok || !pyval.Truthy(session["date"]) {
			return nil, validation("next_program sessions must contain dates")
		}
		if !isoDate(pyval.Str(session["date"])) {
			return nil, validation("next_program session dates must be ISO dates")
		}
		switch session["status"] {
		case "logged", "completed", "skipped":
			return nil, validation("next_program cannot contain completed sessions")
		}
		if pyval.Truthy(session["completed"]) {
			return nil, validation("next_program cannot contain completed sessions")
		}
		normalized := pyval.CopyMap(session)
		id := normalized["id"]
		if !pyval.Truthy(id) {
			id = normalized["session_id"]
		}
		if pyval.Truthy(id) {
			text := pyval.Str(id)
			if seen[text] {
				return nil, validation("next_program session identities must be unique")
			}
			seen[text] = true
			normalized["id"] = text
		}
		normalized["week_number"] = int64(max(1, sessionWeek(normalized)))
		result.sessions = append(result.sessions, normalized)
	}
	minimum := 1
	first := true
	consider := func(week int) {
		if first || week < minimum {
			minimum = week
			first = false
		}
	}
	for _, phase := range result.phases {
		consider(int(phase["start_week"].(int64)))
	}
	for _, session := range result.sessions {
		if week := int(session["week_number"].(int64)); week > 0 {
			consider(week)
		}
	}
	offset := minimum - 1
	for _, phase := range result.phases {
		phase["start_week"] = phase["start_week"].(int64) - int64(offset)
		phase["end_week"] = phase["end_week"].(int64) - int64(offset)
	}
	for _, session := range result.sessions {
		if week := session["week_number"].(int64); week > 0 {
			session["week_number"] = week - int64(offset)
		}
	}
	return result, nil
}

func listArg(source map[string]any, key string) ([]any, bool) {
	value, present := source[key]
	if !present {
		return nil, true
	}
	list, ok := value.([]any)
	return list, ok
}

func canonicalMaxes(maxes map[string]any) map[string]any {
	aliases := map[string]string{"squat_kg": "squat", "bench_kg": "bench", "deadlift_kg": "deadlift", "dl_kg": "deadlift"}
	out := make(map[string]any, len(maxes))
	for key, value := range maxes {
		name := key
		if alias, ok := aliases[key]; ok {
			name = alias
		}
		out[name] = value
	}
	return out
}

func archiveBlockID(d *Deps, name any, blocks, phases, sessions []map[string]any) string {
	slug := strings.Trim(nonAlnum.ReplaceAllString(strings.ToLower(pyval.Str2(name)), "-"), "-")
	if len(slug) > 48 {
		slug = slug[:48]
	}
	slug = strings.Trim(slug, "-")
	if slug == "" || reservedName(slug) {
		return "block-" + d.Env.Hex()[:16]
	}
	taken := map[string]bool{}
	for _, group := range [][]map[string]any{blocks, phases, sessions} {
		for _, item := range group {
			for _, key := range []string{"id", "block_id", "block"} {
				if pyval.Truthy(item[key]) {
					taken[pyval.Str(item[key])] = true
				}
			}
		}
	}
	candidate := slug
	for suffix := 2; taken[candidate]; suffix++ {
		candidate = slug + "-" + pyval.Str(int64(suffix))
	}
	return candidate
}

func idOf(block map[string]any) string {
	return scope.BlockID(block)
}

func blockStatus(block map[string]any) string {
	if status, present := block["status"]; present {
		return pyval.Str(status)
	}
	return "active"
}

func blockTransition(d *Deps, r *Request) (any, error) {
	action := r.String("action")
	blockID := r.String("block_id")
	if action == "rename" {
		return d.renameBlock(r, blockID)
	}
	switch action {
	case "complete", "start_next", "complete_and_start":
	default:
		return nil, validation("action must be complete, start_next, complete_and_start, or rename")
	}
	if blockID == "" {
		return nil, validation("block_id is required")
	}
	starting := action == "start_next" || action == "complete_and_start"
	completing := action == "complete" || action == "complete_and_start"
	if starting {
		if err := validateTransitionStart(r.Args["start_date"], r.Args["week_start_day"], r.Args["start_maxes_kg"]); err != nil {
			return nil, err
		}
	}
	if completing && reservedName(r.Args["current_name"]) {
		return nil, validation("an archived block cannot be named current")
	}
	next, err := validateNextProgram(r.Args["next_program"])
	if err != nil {
		return nil, err
	}
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, r.Selected(), true)
	if err != nil {
		return nil, mapError(err)
	}
	program := pyval.CopyMap(loaded.Program)
	meta := metaOf(program)
	blocks := pyval.Maps(pyval.DeepCopy(meta["blocks"]))
	currentID := pyval.Str2(meta["current_block_id"])
	if currentID == "" {
		for _, block := range blocks {
			if blockStatus(block) == "active" {
				currentID = idOf(block)
				break
			}
		}
	}
	var active map[string]any
	for _, block := range blocks {
		if idOf(block) == currentID && blockStatus(block) == "active" {
			active = block
			break
		}
	}
	if active == nil {
		for _, block := range blocks {
			if idOf(block) == "current" && blockStatus(block) == "active" {
				active = block
				break
			}
		}
	}
	var source map[string]any
	if completing {
		activeID := ""
		if active != nil {
			activeID = idOf(active)
		}
		valid := blockID == activeID || (activeID == "current" && blockID == "current")
		if active == nil || !valid {
			return nil, validation("block_id must identify the active current block")
		}
		source = active
	} else {
		if active != nil {
			return nil, validation("start_next is only allowed after the current block is completed")
		}
		for _, block := range blocks {
			if idOf(block) == blockID && block["status"] == "completed" {
				source = block
				break
			}
		}
		if source == nil {
			return nil, validation("block_id must identify a completed block")
		}
	}
	phases := pyval.Maps(pyval.DeepCopy(program["phases"]))
	sessions := pyval.Maps(pyval.DeepCopy(program["sessions"]))
	sourceID := idOf(source)
	archiveID := sourceID
	if sourceID == "current" {
		naming := r.Args["current_name"]
		if !pyval.Truthy(naming) {
			naming = source["name"]
		}
		archiveID = archiveBlockID(d, naming, blocks, phases, sessions)
	}
	if completing {
		if _, present := source["start_maxes_kg"]; !present {
			source["start_maxes_kg"] = pyval.DeepCopy(orEmptyMap(program["current_maxes"]))
		}
		move := func(items []map[string]any) {
			for _, item := range items {
				block := pyval.Str2(item["block"])
				if block == "" {
					block = "current"
				}
				if block == "current" || pyval.Str2(item["block_id"]) == sourceID {
					item["block"] = archiveID
					item["block_id"] = archiveID
				}
			}
		}
		move(phases)
		move(sessions)
		remapBlockMeta(meta, sourceID, archiveID)
		archiveBlockRecords(program, sourceID, archiveID)
		source["id"] = archiveID
		source["block_id"] = archiveID
		if name, ok := r.Args["current_name"].(string); ok && strings.TrimSpace(name) != "" {
			source["name"] = strings.TrimSpace(name)
		}
		if reservedName(source["name"]) {
			source["name"] = archiveID
		}
		label := pyval.Str2(source["name"])
		if label == "" {
			label = archiveID
		}
		source["label"] = label
		source["status"] = "completed"
		source["archived"] = true
		source["completed_at"] = d.Env.Stamp()
	}
	var nextID any
	if starting {
		identifier := "block-" + d.Env.Hex()[:16]
		nextID = identifier
		nextSessions := make([]map[string]any, 0, len(next.sessions))
		for _, session := range next.sessions {
			prepared := pyval.CopyMap(session)
			prepared["block"] = "current"
			prepared["block_id"] = identifier
			prepared["status"] = "planned"
			prepared["completed"] = false
			nextSessions = append(nextSessions, prepared)
		}
		nextPhases := make([]map[string]any, 0, len(next.phases))
		for _, phase := range next.phases {
			prepared := pyval.CopyMap(phase)
			prepared["block"] = "current"
			prepared["block_id"] = identifier
			nextPhases = append(nextPhases, prepared)
		}
		phases = append(phases, nextPhases...)
		sessions = append(sessions, nextSessions...)
		endWeek := 0
		for _, phase := range nextPhases {
			week, _ := pyval.Truncate(phase["end_week"])
			endWeek = max(endWeek, week)
		}
		for _, session := range nextSessions {
			week, _ := pyval.Truncate(session["week_number"])
			endWeek = max(endWeek, week)
		}
		name := r.Args["name"]
		if !pyval.Truthy(name) {
			name = "Next block"
		}
		blocks = append(blocks, map[string]any{
			"id": identifier, "block_id": identifier, "label": "current", "name": name, "status": "active",
			"start_week": int64(1), "end_week": int64(endWeek), "start_date": r.Args["start_date"],
			"week_start_day": r.Args["week_start_day"], "start_maxes_kg": pyval.DeepCopy(r.Args["start_maxes_kg"]),
		})
		meta["program_start"] = r.Args["start_date"]
		maxes, _ := r.Args["start_maxes_kg"].(map[string]any)
		program["current_maxes"] = canonicalMaxes(maxes)
	}
	meta["blocks"] = pyval.ToList(blocks)
	meta["current_block_id"] = nextID
	program["phases"] = pyval.ToList(phases)
	program["sessions"] = pyval.ToList(sessions)
	result := map[string]any{"action": action, "block_id": blockID, "next_block_id": nextID, "warning": "Unfinished sessions were preserved"}
	written, err := d.Programs.WriteNewVersion(r.Ctx, r.Athlete, program, false)
	if err != nil {
		return nil, mapError(err)
	}
	result["program"] = written.Program
	return result, nil
}

func orEmptyMap(value any) any {
	if value == nil {
		return map[string]any{}
	}
	return value
}

func (d *Deps) renameBlock(r *Request, blockID string) (any, error) {
	name, ok := r.Args["name"].(string)
	if !ok || strings.TrimSpace(name) == "" {
		return nil, validation("rename requires a block name")
	}
	return d.mutateSource(r, r.Selected(), func(program map[string]any) (map[string]any, error) {
		meta := metaOf(program)
		blocks, _ := meta["blocks"].([]any)
		var block map[string]any
		for _, raw := range blocks {
			if candidate, ok := raw.(map[string]any); ok && pyval.Str(firstTruthy(candidate["id"], candidate["block_id"])) == blockID {
				block = candidate
				break
			}
		}
		if block == nil {
			return nil, validation("block_id must identify an existing block")
		}
		if block["status"] == "completed" && reservedName(name) {
			return nil, validation("an archived block cannot be named current")
		}
		block["name"] = strings.TrimSpace(name)
		block["label"] = strings.TrimSpace(name)
		return map[string]any{"action": "rename", "block_id": blockID, "name": block["name"]}, nil
	})
}

func firstTruthy(values ...any) any {
	for _, value := range values {
		if pyval.Truthy(value) {
			return value
		}
	}
	return nil
}

func remapBlockMeta(meta map[string]any, sourceID, archiveID string) {
	notes, _ := meta["block_notes"].([]any)
	for _, raw := range notes {
		note, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		block := pyval.Str2(note["block"])
		if block == sourceID || block == "current" || pyval.Str2(note["block_id"]) == sourceID ||
			(sourceID == "current" && !pyval.Truthy(note["block_id"]) && !pyval.Truthy(note["block"])) {
			note["block"] = archiveID
			note["block_id"] = archiveID
		}
	}
}

func archiveBlockRecords(program map[string]any, sourceID, archiveID string) {
	for _, field := range scope.RecordFields {
		records, _ := program[field].([]any)
		for _, raw := range records {
			record, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			belongs := scope.RecordBlock(record, field, program)
			target := sourceID
			if sourceID == "current" {
				target = scope.CurrentBlockID(program)
			}
			if belongs == sourceID || belongs == target {
				record["block_id"] = archiveID
				if _, present := record["block"]; present {
					record["block"] = archiveID
				}
			}
		}
	}
}
