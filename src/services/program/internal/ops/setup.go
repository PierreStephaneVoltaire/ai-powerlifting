package ops

import (
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"

	"powerlifting/program/internal/pyval"
)

var weekdayOrder = []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}

var isoPattern = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

func weekdayIndex(name string) (int, bool) {
	for index, day := range weekdayOrder {
		if day == name {
			return index, true
		}
	}
	return 0, false
}

func pyWeekday(moment time.Time) int {
	return (int(moment.Weekday()) + 6) % 7
}

func validISODate(value any) (time.Time, bool) {
	text, ok := value.(string)
	if !ok || !isoPattern.MatchString(text) {
		return time.Time{}, false
	}
	parsed, err := time.Parse("2006-01-02", text)
	if err != nil || parsed.Format("2006-01-02") != text {
		return time.Time{}, false
	}
	return parsed, true
}

func positiveMaxes(value any) map[string]float64 {
	out := map[string]float64{}
	maxes, ok := value.(map[string]any)
	if !ok {
		return out
	}
	for key, raw := range maxes {
		var number float64
		switch typed := raw.(type) {
		case string:
			parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
			if err != nil {
				continue
			}
			number = parsed
		case bool, int, int64, float64:
			number, _ = pyval.Float(typed)
		default:
			continue
		}
		if number > 0 {
			out[key] = number
		}
	}
	return out
}

func setupPhases(template map[string]any) []map[string]any {
	if template != nil {
		var phases []map[string]any
		list, _ := template["phases"].([]any)
		for _, raw := range list {
			phase, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			name := phase["name"]
			if !pyval.Truthy(name) {
				name = "Base"
			}
			intent := phase["intent"]
			if !pyval.Truthy(intent) {
				intent = ""
			}
			built := map[string]any{
				"name": name, "intent": intent,
				"start_week": int64(weekOf(phase, "week_start", "start_week")),
				"end_week":   int64(weekOf(phase, "week_end", "end_week")),
				"block":      "current",
			}
			if phase["target_rpe_min"] != nil {
				built["target_rpe_min"] = phase["target_rpe_min"]
			}
			if phase["target_rpe_max"] != nil {
				built["target_rpe_max"] = phase["target_rpe_max"]
			}
			phases = append(phases, built)
		}
		if len(phases) > 0 {
			return phases
		}
	}
	return []map[string]any{{"name": "Base", "intent": "Initial setup block", "start_week": int64(1), "end_week": int64(4), "block": "current"}}
}

func weekOf(phase map[string]any, primary, secondary string) int {
	for _, key := range []string{primary, secondary} {
		if pyval.Truthy(phase[key]) {
			number, _ := pyval.Truncate(phase[key])
			return number
		}
	}
	return 1
}

func roundToPlate(kg float64) float64 {
	return math.RoundToEven(kg/2.5) * 2.5
}

func rpeToPercent(reps, rpe any) (float64, bool) {
	repsValue, ok1 := floatOf(reps)
	rpeValue, ok2 := floatOf(rpe)
	if !ok1 || !ok2 || repsValue <= 0 || rpeValue <= 0 {
		return 0, false
	}
	effective := repsValue + math.Max(0, 10-rpeValue)
	return 1 / (1 + effective/30), true
}

func floatOf(value any) (float64, bool) {
	if value == nil {
		return 0, false
	}
	if text, ok := value.(string); ok {
		parsed, err := strconv.ParseFloat(strings.TrimSpace(text), 64)
		return parsed, err == nil
	}
	return pyval.Float(value)
}

func dayOffset(session map[string]any, startIndex int) int {
	if name, ok := session["day_of_week"].(string); ok {
		if index, found := weekdayIndex(name); found {
			return ((index-startIndex)%7 + 7) % 7
		}
	}
	raw, present := session["day_index"]
	if !present {
		raw = int64(0)
	}
	index, ok := pyval.Truncate(raw)
	if !ok || raw == nil {
		return 0
	}
	if index >= 1 && index <= 7 {
		return index - 1
	}
	return max(0, min(6, index))
}

func concretize(template map[string]any, maxes map[string]float64, start time.Time, weekStartDay string) []map[string]any {
	startIndex, found := weekdayIndex(capitalize(strings.TrimSpace(weekStartDay)))
	if !found {
		startIndex = 0
	}
	anchor := start.AddDate(0, 0, -((pyWeekday(start)-startIndex)%7+7)%7)
	templates, _ := template["sessions"].([]any)
	var sessions []map[string]any
	for _, raw := range templates {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		weekNumber := 1
		if pyval.Truthy(item["week_number"]) {
			weekNumber, _ = pyval.Truncate(item["week_number"])
		}
		date := anchor.AddDate(0, 0, (weekNumber-1)*7+dayOffset(item, startIndex))
		if date.Before(start) {
			continue
		}
		exercises := []any{}
		list, _ := item["exercises"].([]any)
		for _, rawExercise := range list {
			exercise, ok := rawExercise.(map[string]any)
			if !ok {
				continue
			}
			exercises = append(exercises, concreteExercise(exercise, maxes))
		}
		week := item["label"]
		if _, present := item["label"]; !present {
			week = "W" + strconv.Itoa(weekNumber)
		}
		sessions = append(sessions, map[string]any{
			"date": date.Format("2006-01-02"), "day": date.Weekday().String(), "week": week, "week_number": int64(weekNumber),
			"status": "planned", "completed": false, "planned_exercises": exercises, "exercises": []any{}, "session_notes": "",
		})
	}
	return sessions
}

func concreteExercise(exercise map[string]any, maxes map[string]float64) map[string]any {
	gid := exercise["glossary_id"]
	loadType := "unresolvable"
	if value, present := exercise["load_type"]; present {
		loadType = pyval.Str(value)
	}
	value := exercise["load_value"]
	var kg any
	source := loadType
	gidText, _ := gid.(string)
	e1rm, hasMax := maxes[gidText]
	switch {
	case loadType == "percentage" && pyval.Truthy(value):
		if hasMax && e1rm != 0 {
			load, _ := pyval.Float(value)
			kg = roundToPlate(e1rm * load)
		} else {
			source = "unresolvable"
		}
	case loadType == "absolute":
		kg = value
	case loadType == "rpe":
		percent, ok := rpeToPercent(exercise["reps"], exercise["rpe_target"])
		if hasMax && e1rm != 0 && ok {
			kg = roundToPlate(e1rm * percent)
			source = "rpe_estimate"
		} else {
			source = "unresolvable"
		}
	}
	notes := exercise["notes"]
	if _, present := exercise["notes"]; !present {
		notes = ""
	}
	return map[string]any{
		"name": exercise["name"], "glossary_id": gid, "sets": exercise["sets"], "reps": exercise["reps"],
		"kg": kg, "rpe_target": exercise["rpe_target"], "load_source": source, "notes": notes,
	}
}

func templateVisible(template map[string]any, person string, aliases map[string]bool) bool {
	meta, ok := template["meta"].(map[string]any)
	if !ok {
		meta = template
	}
	if published, present := meta["published"]; !present || pyval.Truthy(published) {
		return true
	}
	author := pyval.Str2(meta["author_pk"])
	if author == "" || person == "" {
		return false
	}
	owners := map[string]bool{person: true}
	if aliases[person] {
		owners = aliases
	}
	return owners[author]
}

func ownerAliases(r *Request) map[string]bool {
	out := map[string]bool{}
	if r.Person == "" {
		return out
	}
	for _, value := range []string{r.Person, pyval.Str2(r.Access["settings_pk"]), pyval.Str2(r.Access["own_athlete_pk"])} {
		if value != "" {
			out[value] = true
		}
	}
	return out
}

func numberOrZero(maxes map[string]float64, key string) any {
	if value, ok := maxes[key]; ok {
		return value
	}
	return int64(0)
}

func setupInitialize(d *Deps, r *Request) (any, error) {
	mode := r.String("mode")
	switch mode {
	case "blank", "manual_sessions", "template":
	default:
		return nil, validation("INVALID_SETUP_MODE: mode must be blank, manual_sessions, or template")
	}
	start, ok := validISODate(r.Args["start_date"])
	if !ok {
		return nil, validation("INVALID_START_DATE: start_date must be YYYY-MM-DD")
	}
	startText := r.String("start_date")
	weekStartDay := r.String("week_start_day")
	if !weekdays[weekStartDay] {
		return nil, validation("INVALID_WEEK_START_DAY: week_start_day must be a weekday name")
	}
	_, has, err := d.Programs.SetupCurrentSK(r.Ctx, r.Athlete)
	if err != nil {
		return nil, err
	}
	if has {
		return nil, validation("ALREADY_INITIALIZED: Current program already exists")
	}
	maxes := positiveMaxes(r.Args["maxes"])
	var template map[string]any
	templateSK := r.String("template_sk")
	if mode == "template" {
		if templateSK == "" {
			return nil, validation("TEMPLATE_REQUIRED: template_sk is required for template setup")
		}
		item, err := d.Related.Template(r.Ctx, d.Config.TemplatesLibraryPK, templateSK)
		if err != nil {
			return nil, err
		}
		if item == nil || !templateVisible(item, r.Person, ownerAliases(r)) {
			return nil, validation("TEMPLATE_NOT_FOUND: Template not found")
		}
		template = item
		var missing []any
		required, _ := template["required_maxes"].([]any)
		for _, id := range required {
			if _, present := maxes[pyval.Str(id)]; !present {
				missing = append(missing, pyval.Str(id))
			}
		}
		if len(missing) > 0 {
			return map[string]any{"status": "gate_blocked", "missingMaxes": missing, "templateSk": templateSK, "startDate": startText, "weekStartDay": weekStartDay}, nil
		}
	}
	program := d.setupProgram(r.Athlete, mode, r.String("program_name"), startText, weekStartDay, maxes, template, templateSK, start)
	sessionCount := len(program["sessions"].([]any))
	sk, err := d.Programs.WriteInitial(r.Ctx, r.Athlete, program)
	if err != nil {
		return nil, mapError(err)
	}
	return map[string]any{"status": "initialized", "mode": mode, "programSk": sk, "sessionCount": int64(sessionCount)}, nil
}

func (d *Deps) setupProgram(athlete, mode, programName, startDate, weekStartDay string, maxes map[string]float64, template map[string]any, templateSK string, start time.Time) map[string]any {
	now := d.Env.Stamp()
	squat, bench, deadlift := numberOrZero(maxes, "squat"), numberOrZero(maxes, "bench"), numberOrZero(maxes, "deadlift")
	total := maxes["squat"] + maxes["bench"] + maxes["deadlift"]
	var totalValue any = float64(0.45)
	if total > 0 {
		totalValue = total
	} else if len(maxes) == 0 {
		totalValue = float64(0.45)
	}
	name := strings.TrimSpace(programName)
	if name == "" {
		name = "Getting Started"
	}
	note := "Initialized from onboarding"
	if mode == "template" {
		note = "Initialized from starter template"
	}
	phases := setupPhases(template)
	endWeek := 1
	for _, phase := range phases {
		week, _ := pyval.Truncate(phase["end_week"])
		endWeek = max(endWeek, week)
	}
	startMaxes := map[string]any{}
	for _, lift := range []string{"squat", "bench", "deadlift"} {
		if value, present := maxes[lift]; present && value != 0 {
			startMaxes[lift] = value
		}
	}
	orNil := func(key string) any {
		if value, present := maxes[key]; present && value != 0 {
			return value
		}
		return nil
	}
	var sessions []any
	if template != nil {
		for _, session := range concretize(template, maxes, start, weekStartDay) {
			session["id"] = d.Env.UUID()
			session["block"] = "current"
			setDefault(session, "session_rpe", nil)
			setDefault(session, "body_weight_kg", nil)
			sessions = append(sessions, session)
		}
	}
	if sessions == nil {
		sessions = []any{}
	}
	phaseList := make([]any, len(phases))
	for index, phase := range phases {
		phaseList[index] = phase
	}
	meta := map[string]any{
		"program_name": name, "program_start": startDate, "federation": "", "practicing_for": "", "version_label": "v001",
		"weight_class_kg": int64(0), "weight_class_confirm_by": "", "current_body_weight_kg": int64(0), "current_body_weight_lb": int64(0),
		"target_squat_kg": squat, "target_bench_kg": bench, "target_dl_kg": deadlift, "target_total_kg": totalValue,
		"attempt_pct":    map[string]any{"opener": 0.9, "second": 0.955, "third": 1.0},
		"training_notes": []any{},
		"change_log":     []any{map[string]any{"action": "initialized", "date": now, "note": note}},
		"block_notes":    []any{}, "updated_at": now,
		"manual_maxes": map[string]any{"squat": squat, "bench": bench, "deadlift": deadlift},
		"blocks": []any{map[string]any{
			"id": "current", "block_id": "current", "label": "current", "name": name, "status": "active",
			"start_week": int64(1), "end_week": int64(endWeek), "start_date": startDate, "week_start_day": weekStartDay, "start_maxes_kg": startMaxes,
		}},
		"current_block_id": "current",
	}
	if template != nil && templateSK != "" {
		meta["template_lineage"] = map[string]any{"applied_template_sk": templateSK, "applied_at": now, "week_start_day": weekStartDay, "start_date": startDate}
	}
	return map[string]any{
		"pk": athlete, "sk": "program#v001", "meta": meta, "phases": phaseList, "sessions": sessions,
		"goals": []any{map[string]any{
			"id": d.Env.UUID(), "title": "Lift 1 lb", "goal_type": "coach_defined", "priority": "optional",
			"target_total_kg": 0.45, "strategy_mode": "train_through", "risk_tolerance": "low",
		}},
		"diet_notes": []any{}, "supplements": []any{}, "supplement_phases": []any{}, "lift_profiles": []any{},
		"current_maxes": map[string]any{"squat": orNil("squat"), "bench": orNil("bench"), "deadlift": orNil("deadlift"), "method": "manual"},
	}
}

func setDefault(session map[string]any, key string, value any) {
	if _, present := session[key]; !present {
		session[key] = value
	}
}
