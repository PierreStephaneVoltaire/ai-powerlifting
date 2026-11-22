package render

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"sort"
	"strings"
)

//go:embed calculation_constants.json
var calculationConstants []byte

var scores struct {
	RPE  map[string]float64                       `json:"rpe_percent"`
	DOTS map[string]map[string]float64            `json:"dots_coefficients"`
	IPF  map[string]map[string]map[string]float64 `json:"ipf_gl_coefficients"`
}

func init() {
	if err := json.Unmarshal(calculationConstants, &scores); err != nil {
		panic(err)
	}
}

var parentheses = regexp.MustCompile(`\s*\(.*?\)\s*`)

func mainLift(name string) string {
	words := strings.Fields(strings.ToLower(parentheses.ReplaceAllString(name, " ")))
	for i, word := range words {
		if strings.HasSuffix(word, "sses") || strings.HasSuffix(word, "ches") || strings.HasSuffix(word, "shes") || strings.HasSuffix(word, "xes") {
			words[i] = word[:len(word)-2]
		} else if strings.HasSuffix(word, "s") && !strings.HasSuffix(word, "ss") {
			words[i] = word[:len(word)-1]
		}
	}
	name = strings.Join(words, " ")
	if strings.Contains(name, "squat") && !strings.Contains(name, "hack") && !strings.Contains(name, "split") {
		return "squat"
	}
	if name == "bench press" || name == "bench" || name == "pause bench press" || name == "paused bench press" || name == "competition bench press" {
		return "bench"
	}
	if strings.Contains(name, "deadlift") && !strings.Contains(name, "rdl") && !strings.Contains(name, "romanian") {
		return "deadlift"
	}
	return ""
}

func bestE1RM(exercise map[string]any, sessionRPE any) float64 {
	rpe := exercise["rpe"]
	if rpe == nil {
		rpe = sessionRPE
	}
	sets := list(exercise["sets_data"])
	if len(sets) == 0 {
		sets = []any{exercise}
	}
	statuses := list(exercise["set_statuses"])
	best := 0.0
	for i, raw := range sets {
		if i < len(statuses) && (statuses[i] == "pending" || statuses[i] == "skipped") {
			continue
		}
		set := record(raw)
		weight, ok := number(set["kg"])
		if !ok || weight <= 0 {
			continue
		}
		reps, ok := number(set["reps"])
		if !ok || reps != math.Trunc(reps) || reps < 1 || reps > 10 {
			continue
		}
		level := rpe
		if set["rpe"] != nil {
			level = set["rpe"]
		}
		levelNumber := 10.0
		if level != nil {
			var valid bool
			levelNumber, valid = number(level)
			if !valid || levelNumber < 6 || levelNumber > 10 {
				continue
			}
		}
		pct := scores.RPE[fmt.Sprintf("%d-%d", int(reps), int(levelNumber))]
		if pct > 0 {
			best = math.Max(best, math.Round(weight/pct*10)/10)
		}
	}
	return best
}

type scoreWeek struct {
	lifts  map[string]float64
	weight float64
	date   string
}

func (b block) scoreTrendRows() []Row {
	weeks := map[int]*scoreWeek{}
	for _, session := range sortedSessions(sessionList(b.bundle["sessions"])) {
		completed, _ := session["completed"].(bool)
		block, sessionBlock := text(b.meta["block"]), text(session["block"])
		week, ok := number(session["week_number"])
		if !completed || !ok || week < 1 || week != math.Trunc(week) || !b.inWindow(text(session["date"])) || (block != "" && sessionBlock != block) {
			continue
		}
		if start, ok := number(b.meta["weekStart"]); ok && week < start {
			continue
		}
		if end, ok := number(b.meta["weekEnd"]); ok && week > end {
			continue
		}
		item := weeks[int(week)]
		if item == nil {
			item = &scoreWeek{lifts: map[string]float64{}, date: text(session["date"])}
			weeks[int(week)] = item
		}
		if weight, ok := number(session["body_weight_kg"]); ok && weight > item.weight {
			item.weight = weight
		}
		for _, raw := range list(session["exercises"]) {
			exercise := record(raw)
			lift := mainLift(text(exercise["name"]))
			if lift != "" {
				item.lifts[lift] = math.Max(item.lifts[lift], bestE1RM(exercise, session["session_rpe"]))
			}
		}
	}
	keys := make([]int, 0, len(weeks))
	for key := range weeks {
		keys = append(keys, key)
	}
	sort.Ints(keys)
	rows := []Row{{"Week", "Squat kg", "Bench kg", "Deadlift kg", "Total kg", "DOTS", "IPF GL", "IPF GL mode", "Squat change kg", "Bench change kg", "Deadlift change kg"}}
	sex := text(b.bundle["athleteSex"])
	for _, week := range keys {
		item := weeks[week]
		squat, bench, deadlift := item.lifts["squat"], item.lifts["bench"], item.lifts["deadlift"]
		total := squat + bench + deadlift
		if total == 0 {
			continue
		}
		weight := item.weight
		if weight <= 0 {
			weight = b.nearestWeight(item.date)
		}
		var dots, ipf any
		mode := ""
		if c, ok := scores.DOTS[sex]; ok && weight > 0 {
			denominator := c["a"] + c["b"]*weight + c["c"]*math.Pow(weight, 2) + c["d"]*math.Pow(weight, 3) + c["e"]*math.Pow(weight, 4)
			if math.Abs(denominator) < 1e-12 {
				dots = 0
			} else {
				dots = math.Round(500*total/denominator*100) / 100
			}
			result := 0.0
			if squat > 0 && bench > 0 && deadlift > 0 {
				mode = "classic_powerlifting"
				result = total
			} else if squat == 0 && bench > 0 && deadlift == 0 {
				mode = "classic_bench"
				result = bench
			}
			if mode != "" {
				coeff := scores.IPF[mode][sex]
				denominator = coeff["a"] - coeff["b"]*math.Exp(-coeff["c"]*weight)
				if math.Abs(denominator) >= 1e-12 {
					ipf = math.Round(result*100/denominator*100) / 100
				}
			}
		}
		present := func(value float64) any {
			if value == 0 {
				return nil
			}
			return value
		}
		previous := weeks[week-1]
		delta := func(lift string) any {
			if previous == nil || item.lifts[lift] == 0 || previous.lifts[lift] == 0 {
				return nil
			}
			return math.Round((item.lifts[lift]-previous.lifts[lift])*10) / 10
		}
		rows = append(rows, Row{week, present(squat), present(bench), present(deadlift), math.Round(total*10) / 10, dots, ipf, mode, delta("squat"), delta("bench"), delta("deadlift")})
	}
	if len(rows) == 1 {
		return nil
	}
	return rows
}

func (b block) nearestWeight(date string) float64 {
	latest := ""
	weight := 0.0
	for _, raw := range list(b.bundle["weightLog"]) {
		entry := record(raw)
		entryDate := text(entry["date"])
		kg, ok := number(entry["kg"])
		if ok && kg > 0 && entryDate <= date && entryDate >= latest {
			latest, weight = entryDate, kg
		}
	}
	for _, session := range sortedSessions(sessionList(b.bundle["sessions"])) {
		entryDate := text(session["date"])
		kg, ok := number(session["body_weight_kg"])
		block, sessionBlock := text(b.meta["block"]), text(session["block"])
		if ok && kg > 0 && text(session["status"]) != "skipped" && b.inWindow(entryDate) && (block == "" || sessionBlock == block) && entryDate <= date && entryDate >= latest {
			latest, weight = entryDate, kg
		}
	}
	return weight
}
