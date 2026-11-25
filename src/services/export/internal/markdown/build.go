package markdown

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	"powerlifting/export/internal/calc"
	"powerlifting/export/internal/liftprofile"
	"powerlifting/export/internal/values"
)

type Input struct {
	Program     M
	Weekly      M
	LiftOrder   []string
	WeightLog   []M
	MaxHistory  []M
	Federations M
	Correlation M
	Evaluation  M
	PK          string
	Version     string
	Sex         string
	Today       time.Time
}

var failedReasonLabels = map[string]string{
	"strength_failure": "Strength failure", "technical_failure": "Technical failure", "command_failure": "Command failure",
	"grip": "Grip", "depth": "Depth", "pause": "Pause", "lockout": "Lockout", "balance": "Balance", "pain": "Pain",
	"fatigue": "Fatigue", "misload_bad_attempt_selection": "Misload / bad attempt selection",
}

var missReasonLabels = func() map[string]string {
	out := map[string]string{"equipment_issue": "Equipment issue"}
	for key, value := range failedReasonLabels {
		out[key] = value
	}
	return out
}()

var missCategoryLabels = map[string]string{
	"strength": "Strength", "judged_technical": "Judged technical", "command": "Command", "attempt_selection": "Attempt selection",
	"pain": "Pain", "fatigue": "Fatigue", "equipment": "Equipment", "other": "Other",
}

var liftLabels = map[string]string{"squat": "Squat", "bench": "Bench", "deadlift": "Deadlift"}

func failedSetReasons(value any) string {
	list, ok := value.([]any)
	if !ok {
		return ""
	}
	var chunks []string
	for index, raw := range list {
		reasons, ok := raw.([]any)
		if !ok {
			continue
		}
		var labels []string
		for _, reason := range reasons {
			if text, ok := reason.(string); ok {
				if label, found := failedReasonLabels[text]; found {
					labels = append(labels, label)
				}
			}
		}
		if len(labels) > 0 {
			chunks = append(chunks, fmt.Sprintf("set %d: %s", index+1, strings.Join(labels, ", ")))
		}
	}
	return strings.Join(chunks, "; ")
}

func missReasons(value any) string {
	list, ok := value.([]any)
	if !ok {
		return ""
	}
	var labels []string
	for _, reason := range list {
		if text, ok := reason.(string); ok {
			if label, found := missReasonLabels[text]; found {
				labels = append(labels, label)
			}
		}
	}
	return strings.Join(labels, ", ")
}

func Render(in Input) (string, error) {
	program := in.Program
	meta := copyOf(getd(program, "meta", M{}))
	phases := maps(program["phases"])
	sessionsRaw := maps(program["sessions"])
	goals := maps(program["goals"])
	competitions := maps(program["competitions"])
	dietNotes := maps(program["diet_notes"])
	supplements := maps(program["supplements"])
	supplementPhases := maps(program["supplement_phases"])
	liftProfiles := maps(program["lift_profiles"])
	currentMaxes := copyOf(getd(program, "current_maxes", M{}))
	creator := str(firstNonBlank(meta["creator"], in.PK, program["pk"], "operator"))
	sex := strings.ToLower(str(firstNonBlank(meta["sex"], in.Sex, "male")))
	version := strings.TrimSpace(str(firstNonBlank(in.Version, meta["version"], meta["version_label"], "")))
	if version != "" && !strings.HasPrefix(version, "v") && isDigits(version) {
		number, _ := strconv.Atoi(version)
		version = fmt.Sprintf("v%03d", number)
	}
	prepared := prepareSessions(maps(program["sessions"]), in.WeightLog, meta, phases)

	data := sectionData{
		meta: meta, phases: phases, sessions: prepared, rawSessions: sessionsRaw, correlation: in.Correlation, evaluation: in.Evaluation, goals: goals, competitions: competitions, dietNotes: dietNotes,
		supplements: supplements, supplementPhases: supplementPhases, liftProfiles: liftProfiles, currentMaxes: currentMaxes,
		weightLog: in.WeightLog, maxHistory: in.MaxHistory, federations: in.Federations, weekly: in.Weekly, liftOrder: in.LiftOrder, sex: sex,
	}
	sections := []any{
		data.overview(creator, version, nextCompetitionDate(competitions, in.Today)),
		data.goalsSection(),
		data.currentMaxesSection(),
		data.maxHistorySection(),
		data.phasesSection(),
		data.sessionsSection(),
		data.competitionsSection(),
		data.biometricsSection(),
		data.weightLogSection(),
		data.supplementsSection(),
		data.liftProfilesSection(),
		data.analysisSection(),
		data.notesSection(),
	}
	names := []string{"overview", "goals", "maxes", "history", "phases", "sessions", "competitions", "biometrics", "weightlog", "supplements", "liftprofiles", "analysis", "notes"}
	rendered := make([]string, 0, len(sections))
	for index, section := range sections {
		if section == nil {
			continue
		}
		text, err := execute(names[index], section)
		if err != nil {
			return "", err
		}
		text = strings.TrimRight(text, " \t\r\n")
		if text != "" {
			rendered = append(rendered, text)
		}
	}
	document, err := execute("document", rendered)
	if err != nil {
		return "", err
	}
	return strings.TrimRight(document, " \t\r\n") + "\n", nil
}

func isDigits(text string) bool {
	if text == "" {
		return false
	}
	for _, r := range text {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

type sectionData struct {
	meta             M
	phases           []M
	sessions         []M
	rawSessions      []M
	correlation      M
	evaluation       M
	goals            []M
	competitions     []M
	dietNotes        []M
	supplements      []M
	supplementPhases []M
	liftProfiles     []M
	currentMaxes     M
	weightLog        []M
	maxHistory       []M
	federations      M
	weekly           M
	liftOrder        []string
	sex              string
}

func nextCompetitionDate(competitions []M, today time.Time) string {
	var best *M
	var bestDate time.Time
	for index := range competitions {
		entry := competitions[index]
		status := entry["status"]
		if !truthy(status) {
			status = entry["user_status"]
		}
		if status != "confirmed" {
			continue
		}
		raw := str(firstTruthy(entry["date"], entry["start_date"], ""))
		if len(raw) > 10 {
			raw = raw[:10]
		}
		when, ok := parseDate(raw)
		if !ok || !when.After(today) {
			continue
		}
		if best == nil || when.Before(bestDate) {
			best, bestDate = &competitions[index], when
		}
	}
	if best == nil {
		return ""
	}
	return str(firstTruthy((*best)["date"], ""))
}

func firstTruthy(values ...any) any {
	for _, value := range values {
		if truthy(value) {
			return value
		}
	}
	return values[len(values)-1]
}

type overviewView struct {
	Name    string
	Details []string
	Targets []string
	Notes   []string
}

func (d sectionData) overview(creator, version, competition string) any {
	name := str(firstTruthy(d.meta["program_name"], "Training Program"))
	meta := d.meta
	var details []string
	if creator != "" && creator != "operator" {
		details = append(details, "**Creator:** "+creator)
	}
	if version != "" {
		details = append(details, "**Version:** "+version)
	}
	if truthy(meta["program_start"]) {
		details = append(details, "**Started:** "+str(meta["program_start"]))
	}
	if competition != "" {
		details = append(details, "**Competition:** "+competition)
	}
	if truthy(meta["federation"]) {
		details = append(details, "**Federation:** "+str(meta["federation"]))
	}
	if truthy(meta["weight_class_kg"]) {
		details = append(details, "**Weight Class:** "+str(meta["weight_class_kg"])+" kg")
	}
	if truthy(meta["equipment"]) {
		details = append(details, "**Equipment:** "+str(meta["equipment"]))
	}
	if bw := metaBodyweight(meta); truthy(bw) {
		details = append(details, "**Current BW:** "+str(bw)+" kg")
	}
	label := title(d.sex)
	switch d.sex {
	case "male":
		label = "Male"
	case "female":
		label = "Female"
	}
	details = append(details, "**Sex:** "+label)
	view := overviewView{Name: name, Details: details}
	squat, bench, dl, total := meta["target_squat_kg"], meta["target_bench_kg"], meta["target_dl_kg"], meta["target_total_kg"]
	if !blank(squat) || !blank(bench) || !blank(dl) || !blank(total) {
		if !blank(squat) {
			view.Targets = append(view.Targets, "Squat "+str(squat)+" kg")
		}
		if !blank(bench) {
			view.Targets = append(view.Targets, "Bench "+str(bench)+" kg")
		}
		if !blank(dl) {
			view.Targets = append(view.Targets, "Deadlift "+str(dl)+" kg")
		}
		if !blank(total) {
			view.Targets = append(view.Targets, "**Total: "+str(total)+" kg**")
		}
	}
	if notes := meta["training_notes"]; truthy(notes) {
		list, isList := notes.([]any)
		if !isList {
			list = []any{notes}
		}
		for _, note := range list {
			if truthy(note) {
				view.Notes = append(view.Notes, str(note))
			}
		}
		if len(view.Notes) == 0 {
			view.Notes = nil
		}
	}
	return view
}

type goalsView struct {
	HasPrimary   bool
	Primary      string
	HasSecondary bool
	Secondary    string
	Table        string
}

func (d sectionData) goalsSection() any {
	if len(d.goals) == 0 {
		return nil
	}
	view := goalsView{}
	titles := func(priority string) (string, bool) {
		var out []string
		for _, goal := range d.goals {
			if goal["priority"] == priority {
				out = append(out, str(getd(goal, "title", "Untitled")))
			}
		}
		return strings.Join(out, ", "), len(out) > 0
	}
	view.Primary, view.HasPrimary = titles("primary")
	view.Secondary, view.HasSecondary = titles("secondary")
	order := map[string]int{"primary": 0, "secondary": 1, "optional": 2}
	rank := func(goal M) int {
		if value, ok := order[str(goal["priority"])]; ok {
			return value
		}
		return 9
	}
	sorted := sortedStable(d.goals, func(a, b M) bool {
		if rank(a) != rank(b) {
			return rank(a) < rank(b)
		}
		return str(getd(a, "target_date", "")) < str(getd(b, "target_date", ""))
	})
	var rows [][]any
	for _, goal := range sorted {
		var dates []string
		if list, ok := goal["target_competition_dates"].([]any); ok {
			for _, item := range list {
				dates = append(dates, str(item))
			}
		}
		target := firstNonBlank(goal["target_date"], strings.Join(dates, ", "))
		rows = append(rows, []any{getd(goal, "priority", ""), getd(goal, "title", ""), target, firstLine(getd(goal, "notes", ""))})
	}
	view.Table = table([]string{"Priority", "Goal", "Target Date", "Notes"}, rows)
	return view
}

type tableView struct{ Table string }

func (d sectionData) currentMaxesSection() any {
	if len(d.currentMaxes) == 0 {
		return nil
	}
	var rows [][]any
	for _, lift := range values.SortedKeys(d.currentMaxes) {
		value := d.currentMaxes[lift]
		if lift == "_note" || blank(value) {
			continue
		}
		rows = append(rows, []any{title(strings.ReplaceAll(lift, "_", " ")), value})
	}
	if len(rows) == 0 {
		return nil
	}
	return tableView{Table: table([]string{"Lift", "1RM (kg)"}, rows)}
}

func (d sectionData) maxHistorySection() any {
	if len(d.maxHistory) == 0 {
		return nil
	}
	sorted := sortedStable(d.maxHistory, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) })
	var rows [][]any
	for _, entry := range sorted {
		bw := firstNonBlank(entry["bodyweight_kg"], d.meta["current_body_weight_kg"], d.meta["bodyweight_kg"])
		total := firstNonBlank(entry["total_kg"], "")
		var dots any = ""
		if !blank(total) {
			dots = dotsValue(total, bw, d.sex)
		}
		rows = append(rows, []any{getd(entry, "date", ""), getd(entry, "squat_kg", ""), getd(entry, "bench_kg", ""), getd(entry, "deadlift_kg", ""), total, bw, dots, getd(entry, "context", "")})
	}
	return tableView{Table: table([]string{"Date", "Squat", "Bench", "Deadlift", "Total", "BW", "DOTS", "Context"}, rows)}
}

type phaseLine struct {
	Text  string
	Notes string
}

type phasesView struct{ Phases []phaseLine }

func (d sectionData) phasesSection() any {
	if len(d.phases) == 0 {
		return nil
	}
	view := phasesView{}
	for _, phase := range d.phases {
		name := str(getd(phase, "name", "Unnamed Phase"))
		start, end := getd(phase, "start_week", ""), getd(phase, "end_week", "")
		parts := []string{"**" + name + "**"}
		if truthy(start) && truthy(end) {
			parts = append(parts, "Weeks "+str(start)+"–"+str(end))
		}
		if block := phase["block"]; truthy(block) && block != "current" {
			parts = append(parts, "("+str(block)+" block)")
		}
		var sub []string
		rpeMin, rpeMax := phase["target_rpe_min"], phase["target_rpe_max"]
		if !blank(rpeMin) || !blank(rpeMax) {
			sub = append(sub, "RPE "+orQuestion(rpeMin)+"–"+orQuestion(rpeMax))
		}
		if dpw := phase["days_per_week"]; !blank(dpw) {
			sub = append(sub, str(dpw)+" days/week")
		}
		if intent := phase["intent"]; !blank(intent) {
			sub = append(sub, str(intent))
		}
		line := strings.Join(parts, " — ")
		if len(sub) == 0 {
			line += "."
		} else {
			line += ". " + strings.Join(sub, "; ") + "."
		}
		entry := phaseLine{Text: line}
		if truthy(phase["notes"]) {
			entry.Notes = "  " + str(phase["notes"])
		}
		view.Phases = append(view.Phases, entry)
	}
	return view
}

func orQuestion(value any) string {
	if truthy(value) {
		return str(value)
	}
	return "?"
}

type sessionLine struct {
	Header   string
	Wellness string
	Notes    string
	Table    string
	Planned  string
}

type weekView struct {
	Header   string
	Sessions []sessionLine
}

type sessionsView struct{ Weeks []weekView }

func (d sectionData) sessionsSection() any {
	if len(d.sessions) == 0 {
		return nil
	}
	weeks := map[string][]M{}
	var order []string
	for _, session := range d.sessions {
		key := str(firstTruthy(session["week_number"], session["week"], "Unscheduled"))
		if _, seen := weeks[key]; !seen {
			order = append(order, key)
		}
		weeks[key] = append(weeks[key], session)
	}
	weekRank := func(key string) int {
		if isDigits(key) {
			number, _ := strconv.Atoi(key)
			return number
		}
		return 999
	}
	order = sortedStable(order, func(a, b string) bool { return weekRank(a) < weekRank(b) })
	view := sessionsView{}
	for _, key := range order {
		phaseName := ""
		for _, session := range weeks[key] {
			if name := str(getd(session, "phase_name", "")); name != "" {
				phaseName = name
				break
			}
		}
		header := "Week " + key
		if phaseName != "" {
			header += " — " + phaseName
		}
		week := weekView{Header: header}
		for _, session := range weeks[key] {
			week.Sessions = append(week.Sessions, d.sessionLine(session))
		}
		view.Weeks = append(view.Weeks, week)
	}
	return view
}

func (d sectionData) sessionLine(session M) sessionLine {
	parts := []string{"**" + str(getd(session, "date", "No date")) + "**"}
	if day := session["day"]; truthy(day) {
		parts = append(parts, str(day))
	}
	if status := session["status"]; truthy(status) {
		parts = append(parts, "("+str(status)+")")
	}
	if bw := session["body_weight_kg"]; !blank(bw) {
		parts = append(parts, "BW: "+str(bw)+" kg")
	}
	if rpe := session["session_rpe"]; !blank(rpe) {
		parts = append(parts, "Session RPE: "+str(rpe))
	}
	line := sessionLine{Header: strings.Join(parts, " | ")}
	if wellness, ok := session["wellness"].(map[string]any); ok {
		var wellnessParts []string
		for _, key := range []string{"sleep", "energy", "stress", "soreness", "mood"} {
			if value := wellness[key]; !blank(value) {
				wellnessParts = append(wellnessParts, title(key)+": "+str(value))
			}
		}
		if len(wellnessParts) > 0 {
			line.Wellness = "  " + strings.Join(wellnessParts, " | ")
		}
	}
	if truthy(session["session_notes"]) {
		line.Notes = "  _" + str(session["session_notes"]) + "_"
	}
	status := getd(session, "status", "")
	if exercises := maps(session["exercises"]); len(exercises) > 0 && truthy(session["exercises"]) {
		var rows [][]any
		for _, exercise := range exercises {
			failed := ""
			if statuses, ok := exercise["set_statuses"].([]any); ok {
				for _, item := range statuses {
					if item == "failed" {
						failed = " ✗"
					}
				}
			}
			notes := firstLine(getd(exercise, "notes", "")) + failed
			if suffix := failedSetReasons(exercise["failed_set_reasons"]); suffix != "" {
				notes = strings.TrimSpace(notes + " (" + suffix + ")")
			}
			rows = append(rows, []any{getd(exercise, "name", ""), prescription(exercise), exerciseNumber(getd(exercise, "kg", "")), exerciseNumber(getd(exercise, "rpe", "")), notes, status})
		}
		line.Table = table([]string{"Exercise", "Sets x Reps", "kg", "RPE", "Notes", "Status"}, rows)
	}
	if planned := maps(session["planned_exercises"]); len(planned) > 0 {
		var rows [][]any
		for _, exercise := range planned {
			rows = append(rows, []any{getd(exercise, "name", ""), prescription(exercise), exerciseNumber(getd(exercise, "kg", "")), exerciseNumber(getd(exercise, "rpe_target", "")), firstLine(getd(exercise, "notes", "")), status})
		}
		line.Planned = table([]string{"Exercise", "Sets x Reps", "kg", "Target RPE", "Notes", "Status"}, rows)
	}
	return line
}

func timedExercise(exercise M) bool {
	unit := exercise["rep_unit"]
	return unit == "minutes" || unit == "seconds" || exercise["duration_minutes"] != nil
}

func prescription(exercise M) string {
	sets := exerciseNumber(getd(exercise, "sets", ""))
	reps := getd(exercise, "reps", "")
	if timedExercise(exercise) {
		unit := exercise["rep_unit"]
		if unit == nil {
			unit, reps = "minutes", exercise["duration_minutes"]
		}
		label := "min"
		if unit == "seconds" {
			label = "sec"
		}
		return sets + " x " + exerciseNumber(reps) + " " + label
	}
	if exercise["rep_mode"] == "amrap" {
		if !blank(reps) {
			return sets + " x AMRAP (" + exerciseNumber(reps) + ")"
		}
		return sets + " x AMRAP"
	}
	return sets + " x " + exerciseNumber(reps)
}

func exerciseNumber(value any) string {
	if number, ok := value.(float64); ok {
		return strconv.FormatFloat(number, 'f', -1, 64)
	}
	return str(num(value))
}

type competitionView struct {
	Heading string
	Details string
	Targets string
	Results string
	Table   string
	Context string
	Extras  []string
	Notes   string
}

type competitionsView struct{ Items []competitionView }

func (d sectionData) competitionsSection() any {
	if len(d.competitions) == 0 {
		return nil
	}
	names := map[string]any{}
	if list, ok := d.federations["federations"].([]any); ok {
		for _, raw := range list {
			if item, ok := raw.(map[string]any); ok {
				names[str(item["id"])] = firstNonBlank(item["abbreviation"], item["name"], "")
			}
		}
	}
	view := competitionsView{}
	sorted := sortedStable(d.competitions, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) })
	for _, comp := range sorted {
		item := competitionView{Heading: str(getd(comp, "name", "Unnamed Competition")) + " — " + str(getd(comp, "date", ""))}
		var details []string
		if status := getd(comp, "status", ""); truthy(status) {
			details = append(details, "**Status:** "+str(status))
		}
		federation := firstNonBlank(names[str(firstTruthy(comp["federation_id"], ""))], getd(comp, "federation", ""))
		if truthy(federation) {
			details = append(details, "**Federation:** "+str(federation))
		}
		if wc := comp["weight_class_kg"]; truthy(wc) {
			details = append(details, "**Weight Class:** "+str(wc)+" kg")
		}
		if location := comp["location"]; truthy(location) {
			details = append(details, "**Location:** "+str(location))
		}
		item.Details = strings.Join(details, " | ")
		targets := asMap(comp["targets"])
		item.Targets = liftSummary(targets, "Targets", nil, nil)
		results := asMap(comp["results"])
		item.Results = liftSummary(results, "Results", func(total any) string {
			fallback, _ := resolveDateBodyweight(comp["date"], d.sessions, d.weightLog, d.meta)
			bw := firstNonBlank(comp["body_weight_kg"], fallback)
			dots := dotsValue(total, bw, d.sex)
			if truthy(dots) {
				return "**Total: " + str(total) + "** (DOTS: " + str(dots) + ")"
			}
			return "**Total: " + str(total) + "**"
		}, func() string {
			if place := comp["place"]; !blank(place) {
				return "**Place:** " + str(place)
			}
			return ""
		})
		report := asMap(comp["post_meet_report"])
		if attempts, ok := report["attempts"].([]any); ok && len(attempts) > 0 {
			var rows [][]any
			for _, raw := range attempts {
				attempt, ok := raw.(map[string]any)
				if !ok {
					continue
				}
				result := str(firstTruthy(attempt["result"], ""))
				missDetail := ""
				if result == "missed" {
					var parts []string
					if label := missCategoryLabels[str(firstTruthy(attempt["miss_category"], ""))]; label != "" {
						parts = append(parts, label)
					}
					if reasons := missReasons(attempt["miss_reasons"]); reasons != "" {
						parts = append(parts, reasons)
					}
					missDetail = strings.Join(parts, " / ")
				}
				liftName := str(firstTruthy(attempt["lift"], ""))
				label, known := liftLabels[liftName]
				if !known {
					label = str(getd(attempt, "lift", ""))
				}
				rows = append(rows, []any{label + " " + str(getd(attempt, "attempt_number", "")), getd(attempt, "kg", ""), strings.ReplaceAll(result, "_", " "), missDetail})
			}
			item.Table = table([]string{"Attempt", "kg", "Result", "Miss Detail"}, rows)
		}
		if len(report) > 0 {
			var context []string
			if value := report["sleep_hours"]; !blank(value) {
				context = append(context, "Sleep: "+str(value)+"h")
			}
			if value := report["caffeine_mg"]; !blank(value) {
				context = append(context, "Caffeine: "+str(value)+"mg")
			}
			if value := report["attempt_selection_grade"]; !blank(value) {
				context = append(context, "Attempt selection: "+str(value)+"/5")
			}
			if len(context) > 0 {
				item.Context = strings.Join(context, " / ")
			}
			for _, pair := range [][2]string{{"Warm-ups", "warmup_timing"}, {"Travel", "travel_notes"}, {"Food before", "pre_meet_food"}, {"Food during", "during_meet_food"}, {"Caffeine timing", "caffeine_timing"}, {"Equipment", "equipment_issues"}, {"Commands", "commands_missed"}, {"Meet notes", "notes"}} {
				if value := report[pair[1]]; truthy(value) {
					item.Extras = append(item.Extras, "**"+pair[0]+":** "+str(value))
				}
			}
		}
		if notes := comp["notes"]; truthy(notes) {
			item.Notes = str(notes)
		}
		view.Items = append(view.Items, item)
	}
	return view
}

func liftSummary(values M, label string, totalFormat func(any) string, extra func() string) string {
	var parts []string
	for _, pair := range [][2]string{{"squat_kg", "S"}, {"bench_kg", "B"}, {"deadlift_kg", "D"}} {
		if value := values[pair[0]]; !blank(value) {
			parts = append(parts, pair[1]+": "+str(value))
		}
	}
	total := resolveTotal(values)
	if !blank(total) {
		if totalFormat != nil {
			parts = append(parts, totalFormat(total))
		} else {
			parts = append(parts, "**Total: "+str(total)+"**")
		}
	}
	if extra != nil {
		if text := extra(); text != "" {
			parts = append(parts, text)
		}
	}
	if len(parts) == 0 {
		return ""
	}
	return "**" + label + ":** " + strings.Join(parts, " / ")
}

type biometricsView struct {
	Summary  string
	Averages string
	Table    string
}

func (d sectionData) biometricsSection() any {
	if len(d.dietNotes) == 0 {
		return nil
	}
	total := len(d.dietNotes)
	consistent := 0
	for _, note := range d.dietNotes {
		if truthy(note["consistent"]) {
			consistent++
		}
	}
	percent := values.FloatRepr(calc.Round(float64(consistent)/float64(total)*100, 1))
	view := biometricsView{Summary: fmt.Sprintf("Tracking %d entries with %s%% consistency.", total, percent)}
	average := func(key string) (float64, bool) {
		sum, count := 0.0, 0
		for _, note := range d.dietNotes {
			if blank(note[key]) {
				continue
			}
			value, _ := floatOf(num(note[key]))
			sum += value
			count++
		}
		if count == 0 {
			return 0, false
		}
		return sum / float64(count), true
	}
	var parts []string
	for _, spec := range [][3]string{{"avg_daily_calories", "Calories", "kcal"}, {"avg_protein_g", "Protein", "g"}, {"avg_carb_g", "Carbs", "g"}, {"avg_fat_g", "Fat", "g"}} {
		if value, ok := average(spec[0]); ok {
			parts = append(parts, fmt.Sprintf("**%s:** %.0f %s", spec[1], math.RoundToEven(value), spec[2]))
		}
	}
	if value, ok := average("avg_sleep_hours"); ok {
		parts = append(parts, "**Sleep:** "+values.FloatRepr(calc.Round(value, 1))+" hrs/night")
	}
	if len(parts) > 0 {
		view.Averages = "Average daily intake: " + strings.Join(parts, " | ")
	}
	sorted := sortedStable(d.dietNotes, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) })
	var rows [][]any
	for _, note := range sorted {
		rows = append(rows, []any{getd(note, "date", ""), getd(note, "avg_daily_calories", ""), getd(note, "avg_protein_g", ""), getd(note, "avg_carb_g", ""), getd(note, "avg_fat_g", ""), getd(note, "avg_sleep_hours", ""), firstLine(getd(note, "notes", ""))})
	}
	view.Table = table([]string{"Date", "Calories", "Protein", "Carbs", "Fat", "Sleep", "Notes"}, rows)
	return view
}

type weightLogView struct {
	Summary string
	Table   string
	Empty   bool
}

func signed(value float64) string {
	if value > 0 {
		return "+" + values.FloatRepr(value)
	}
	return values.FloatRepr(value)
}

func (d sectionData) weightLogSection() any {
	if len(d.weightLog) == 0 {
		return nil
	}
	sorted := sortedStable(d.weightLog, func(a, b M) bool { return str(getd(a, "date", "")) < str(getd(b, "date", "")) })
	type point struct {
		date string
		kg   any
	}
	var points []point
	for _, entry := range sorted {
		if !blank(entry["kg"]) {
			points = append(points, point{str(getd(entry, "date", "")), entry["kg"]})
		}
	}
	if len(points) == 0 {
		return weightLogView{Empty: true}
	}
	latest, oldest := points[len(points)-1], points[0]
	latestValue, _ := floatOf(latest.kg)
	oldestValue, _ := floatOf(oldest.kg)
	change := calc.Round(latestValue-oldestValue, 1)
	direction := "stable"
	if change > 0.25 {
		direction = "gain"
	} else if change < -0.25 {
		direction = "loss"
	}
	view := weightLogView{Summary: fmt.Sprintf("Started %s kg on %s. Current: %s kg (%s kg, %s). %d entries.", str(oldest.kg), oldest.date, str(latest.kg), signedChange(change), direction, len(points))}
	start := max(0, len(sorted)-20)
	var rows [][]any
	var prev any
	for _, entry := range sorted[start:] {
		kg := getd(entry, "kg", "")
		delta := ""
		if prev != nil && !blank(kg) {
			current, okC := floatOf(kg)
			before, okB := floatOf(prev)
			if okC && okB {
				delta = signed(calc.Round(current-before, 1))
			}
		}
		rows = append(rows, []any{getd(entry, "date", ""), kg, delta, getd(entry, "notes", "")})
		if !blank(kg) {
			prev = kg
		}
	}
	view.Table = table([]string{"Date", "Weight (kg)", "Change", "Notes"}, rows)
	return view
}

func signedChange(change float64) string {
	if change > 0 {
		return "+" + values.FloatRepr(change)
	}
	return values.FloatRepr(change)
}

type supplementsView struct {
	Stack string
	Lines []string
}

func (d sectionData) supplementsSection() any {
	if len(d.supplements) == 0 && len(d.supplementPhases) == 0 {
		return nil
	}
	view := supplementsView{}
	if len(d.supplements) > 0 {
		var stack []string
		for _, supplement := range d.supplements {
			stack = append(stack, strings.TrimSpace(str(getd(supplement, "name", ""))+" "+str(getd(supplement, "dose", ""))))
		}
		view.Stack = strings.Join(stack, ", ")
	}
	phaseRank := func(phase M) int {
		value, _ := intOf(firstTruthy(phase["phase"], int64(0)))
		return value
	}
	for _, phase := range sortedStable(d.supplementPhases, func(a, b M) bool { return phaseRank(a) < phaseRank(b) }) {
		name := str(firstTruthy(phase["phase_name"], "Phase "+str(getd(phase, "phase", ""))))
		start, end := getd(phase, "start_week", ""), getd(phase, "end_week", "")
		weekRange := ""
		if truthy(start) && truthy(end) {
			weekRange = " (Weeks " + str(start) + "–" + str(end) + ")"
		}
		items, _ := phase["items"].([]any)
		if len(items) > 0 {
			var parts []string
			for _, raw := range items {
				item, _ := raw.(map[string]any)
				parts = append(parts, strings.TrimSpace(str(getd(item, "name", ""))+" "+str(getd(item, "dose", ""))))
			}
			view.Lines = append(view.Lines, "**"+name+weekRange+":** "+strings.Join(parts, ", "))
		} else if truthy(phase["notes"]) {
			view.Lines = append(view.Lines, "**"+name+weekRange+":** "+str(phase["notes"]))
		}
	}
	return view
}

type liftProfileLine struct{ Lift, Body string }

type liftProfilesView struct{ Profiles []liftProfileLine }

func (d sectionData) liftProfilesSection() any {
	if len(d.liftProfiles) == 0 {
		return nil
	}
	view := liftProfilesView{}
	for _, profile := range d.liftProfiles {
		lift := title(str(firstTruthy(profile["lift"], "Unknown")))
		var parts []string
		liftName, _ := profile["lift"].(string)
		if technique := liftprofile.TechniqueText(liftName, asMap(firstTruthy(profile["options"], M{}))); technique != "" {
			parts = append(parts, technique)
		}
		if notes := profile["notes"]; !blank(notes) {
			parts = append(parts, "Notes: "+str(notes))
		}
		if volume := profile["volume_tolerance"]; !blank(volume) {
			parts = append(parts, "Volume tolerance: "+str(volume))
		}
		if stimulus := profile["stimulus_coefficient"]; !blank(stimulus) {
			confidence := getd(profile, "stimulus_coefficient_confidence", "")
			suffix := ""
			if truthy(confidence) {
				suffix = " (" + str(confidence) + " confidence)"
			}
			parts = append(parts, "Stimulus coefficient: "+str(stimulus)+suffix)
		}
		if len(parts) > 0 {
			view.Profiles = append(view.Profiles, liftProfileLine{Lift: lift, Body: strings.Join(parts, "; ")})
		}
	}
	return view
}

type noteLine struct{ Source, Context, Note string }

type notesView struct{ Notes []noteLine }

func (d sectionData) notesSection() any {
	var notes []noteLine
	listOf := func(value any) []any {
		if list, ok := value.([]any); ok {
			return list
		}
		if value == nil {
			return nil
		}
		return []any{value}
	}
	for _, note := range listOf(d.meta["training_notes"]) {
		if truthy(note) {
			notes = append(notes, noteLine{"Program", str(getd(d.meta, "updated_at", "")), str(note)})
		}
	}
	for _, raw := range listOf(d.meta["block_notes"]) {
		note, ok := raw.(map[string]any)
		if ok && truthy(note["notes"]) {
			notes = append(notes, noteLine{"Program", str(firstTruthy(note["date"], getd(note, "updated_at", ""))), str(note["notes"])})
		}
	}
	for _, phase := range d.phases {
		if truthy(phase["notes"]) {
			notes = append(notes, noteLine{"Phase", "W" + str(getd(phase, "start_week", "")) + "–W" + str(getd(phase, "end_week", "")), str(phase["notes"])})
		}
	}
	for _, note := range d.dietNotes {
		if truthy(note["notes"]) {
			notes = append(notes, noteLine{"Biometrics", str(getd(note, "date", "")), str(note["notes"])})
		}
	}
	for _, phase := range d.supplementPhases {
		if truthy(phase["notes"]) {
			notes = append(notes, noteLine{"Supplements", str(getd(phase, "phase_name", "")), str(phase["notes"])})
		}
		items, _ := phase["items"].([]any)
		for _, raw := range items {
			item, _ := raw.(map[string]any)
			if truthy(item["notes"]) {
				notes = append(notes, noteLine{"Supplements", str(getd(item, "name", "")), str(item["notes"])})
			}
		}
	}
	if len(notes) == 0 {
		return nil
	}
	return notesView{Notes: notes}
}
