package views

import (
	"math"
	"sort"
	"strconv"
	"strings"

	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/value"
)

type dotsSet struct{ a, b, c, d, e float64 }

var dotsCoefficients = map[string]dotsSet{
	"male":   {-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -1.093e-06},
	"female": {-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -1.0706e-06},
}

func dots(total, bodyweight float64, sex string) (float64, bool) {
	set, ok := dotsCoefficients[sex]
	if !ok || total <= 0 || bodyweight <= 0 || math.IsNaN(total) || math.IsInf(total, 0) || math.IsInf(bodyweight, 0) {
		return 0, false
	}
	denominator := set.a + set.b*bodyweight + set.c*math.Pow(bodyweight, 2) + set.d*math.Pow(bodyweight, 3) + set.e*math.Pow(bodyweight, 4)
	if math.Abs(denominator) < 1e-12 {
		return 0, true
	}
	rounded, err := strconv.ParseFloat(strconv.FormatFloat(500*total/denominator, 'f', 2, 64), 64)
	if err != nil {
		return 500 * total / denominator, true
	}
	return rounded, true
}

func asMap(v any) map[string]any {
	m, _ := v.(map[string]any)
	if m == nil {
		return map[string]any{}
	}
	return m
}

func asList(v any) []any {
	l, _ := v.([]any)
	return l
}

func hasCompletedSet(exercise map[string]any) bool {
	count := 0
	if n, ok := numOf(value.Or(exercise["sets"], 0)); ok {
		count = max(0, roundEven(n.F))
	}
	statuses := asList(exercise["set_statuses"])
	if len(statuses) > 0 {
		for i := 0; i < count; i++ {
			if i < len(statuses) && (statuses[i] == nil || statuses[i] == "completed") {
				return true
			}
		}
		return false
	}
	return count > 0
}

func bestSessionLift(sessions []map[string]any, lift string) (Num, bool) {
	var best Num
	found := false
	for _, session := range sessions {
		if !value.Truthy(session["completed"]) || session["status"] == "skipped" {
			continue
		}
		for _, entry := range asList(session["exercises"]) {
			exercise := asMap(entry)
			kg, ok := numOf(exercise["kg"])
			if !ok || kg.F == 0 || (found && kg.F <= best.F) || (!found && kg.F <= 0) {
				continue
			}
			if !hasCompletedSet(exercise) {
				continue
			}
			if strings.Contains(strings.ToLower(value.Str(value.Or(exercise["name"], ""))), lift) {
				best, found = kg, true
			}
		}
	}
	return best, found && best.F > 0
}

func resolvedLift(program map[string]any, sessions []map[string]any, lift string) (Num, bool) {
	if n, ok := positive(asMap(program["current_maxes"])[lift]); ok {
		return n, true
	}
	if n, ok := positive(asMap(asMap(program["meta"])["manual_maxes"])[lift]); ok {
		return n, true
	}
	return bestSessionLift(sessions, lift)
}

func latestBodyweight(sessions []map[string]any) (Num, bool) {
	var candidates []map[string]any
	for _, session := range sessions {
		if n, ok := numOf(session["body_weight_kg"]); ok && n.F > 0 {
			candidates = append(candidates, session)
		}
	}
	if len(candidates) == 0 {
		return Num{}, false
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		return value.Str(value.Or(candidates[i]["date"], "")) > value.Str(value.Or(candidates[j]["date"], ""))
	})
	n, _ := numOf(candidates[0]["body_weight_kg"])
	return n, true
}

type Summary struct {
	Squat, Bench, Deadlift, Total, Bodyweight *Num
	Dots                                      *float64
	Videos                                    []any
}

func buildSummary(owner map[string]any, program map[string]any, sessions []map[string]any) Summary {
	meta := asMap(program["meta"])
	var out Summary
	lifts := [3]*Num{}
	for i, lift := range people.Lifts {
		if n, ok := resolvedLift(program, sessions, lift); ok {
			copyN := n
			lifts[i] = &copyN
		}
	}
	out.Squat, out.Bench, out.Deadlift = lifts[0], lifts[1], lifts[2]
	if lifts[0] != nil && lifts[1] != nil && lifts[2] != nil {
		total := lifts[0].Add(*lifts[1]).Add(*lifts[2])
		out.Total = &total
	}
	if n, ok := positive(meta["current_body_weight_kg"]); ok {
		out.Bodyweight = &n
	} else if n, ok := latestBodyweight(sessions); ok {
		out.Bodyweight = &n
	}
	sex := value.Or(meta["sex"], owner["sex"])
	if out.Total != nil && out.Bodyweight != nil && (sex == "male" || sex == "female") {
		if score, ok := dots(out.Total.F, out.Bodyweight.F, sex.(string)); ok {
			out.Dots = &score
		}
	}
	type libraryItem struct {
		video    map[string]any
		date     string
		uploaded string
		entry    map[string]any
	}
	var library []libraryItem
	for _, session := range sessions {
		for _, entry := range asList(session["videos"]) {
			video := asMap(entry)
			item := map[string]any{
				"video":        entry,
				"session_id":   value.Or(session["id"], session["session_id"]),
				"session_date": session["date"],
				"day":          session["day"],
				"week_number":  session["week_number"],
				"phase_name":   value.Or(asMap(session["phase"])["name"], ""),
			}
			library = append(library, libraryItem{video: video, date: value.Str(value.Or(session["date"], "")), uploaded: value.Str(value.Or(video["uploaded_at"], "")), entry: item})
		}
	}
	sort.SliceStable(library, func(i, j int) bool {
		if library[i].date != library[j].date {
			return library[i].date > library[j].date
		}
		return library[i].uploaded > library[j].uploaded
	})
	for _, item := range library {
		out.Videos = append(out.Videos, item.entry)
	}
	return out
}

func (n *Num) value() any {
	if n == nil {
		return nil
	}
	return n.JSON()
}

func (s Summary) Map() map[string]any {
	score := any(nil)
	if s.Dots != nil {
		score = people.FloatValue(*s.Dots)
	}
	return map[string]any{
		"squat_kg": s.Squat.value(), "bench_kg": s.Bench.value(), "deadlift_kg": s.Deadlift.value(),
		"total_kg": s.Total.value(), "bodyweight_kg": s.Bodyweight.value(), "dots": score,
	}
}
