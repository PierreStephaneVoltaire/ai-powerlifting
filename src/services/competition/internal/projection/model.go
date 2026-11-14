package projection

import (
	"encoding/json"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"
)

type Day = time.Time

func ParseDay(text string) (Day, bool) {
	parsed, err := time.Parse("2006-01-02", text)
	return parsed, err == nil
}

func daysBetween(later, earlier Day) int64 {
	return int64(later.Sub(earlier) / (24 * time.Hour))
}

func floorDiv(value, divisor int64) int64 {
	quotient := value / divisor
	if value%divisor != 0 && (value < 0) != (divisor < 0) {
		quotient--
	}
	return quotient
}

type Lift int

const (
	Squat Lift = iota
	Bench
	Deadlift
)

var lifts = [3]Lift{Squat, Bench, Deadlift}

func (l Lift) Key() string {
	return [3]string{"squat", "bench", "deadlift"}[l]
}

func liftFromName(key string) (Lift, bool) {
	switch key {
	case "squat":
		return Squat, true
	case "bench press", "bench":
		return Bench, true
	case "deadlift":
		return Deadlift, true
	}
	return 0, false
}

func isPrimary(key string) bool { return key == "squat" || key == "deadlift" }

type Maxes struct {
	value [3]float64
	set   [3]bool
}

func (m *Maxes) Set(lift Lift, value float64) {
	m.value[lift], m.set[lift] = value, true
}

func (m Maxes) Get(lift Lift) (float64, bool) { return m.value[lift], m.set[lift] }

func (m Maxes) Empty() bool { return !m.set[0] && !m.set[1] && !m.set[2] }

type Exercise struct {
	Key      string
	Kg       float64
	Reps     float64
	Sets     float64
	RPE      *float64
	Statuses []string
}

func (e Exercise) FailedSets() int {
	count := 0
	for _, status := range e.Statuses {
		if status == "failed" {
			count++
		}
	}
	return count
}

func (e Exercise) ExecutedSets() float64 {
	if len(e.Statuses) == 0 {
		return e.Sets
	}
	count := 0
	for _, status := range e.Statuses {
		if status == "completed" || status == "failed" {
			count++
		}
	}
	return float64(count)
}

func (e Exercise) ExecutedVolume() float64 { return e.ExecutedSets() * e.Reps * e.Kg }

func (e Exercise) RepsInt() int { return int(math.Trunc(e.Reps)) }

type Session struct {
	DateText   string
	Date       *Day
	WeekNumber *int64
	Completed  bool
	Status     string
	SessionRPE *float64
	Exercises  []Exercise
}

func (s Session) Week(programStart string) (int64, bool) {
	if s.WeekNumber != nil {
		return *s.WeekNumber, true
	}
	start, ok := ParseDay(programStart)
	if !ok || s.Date == nil {
		return 0, false
	}
	return max(floorDiv(daysBetween(*s.Date, start), 7)+1, 1), true
}

type Competition struct {
	DateText string
	Date     *Day
	Status   string
	Results  map[string]any
}

func (c Competition) resultKg(key string) (float64, bool) {
	value, present := c.Results[key]
	if !present || value == nil {
		return 0, false
	}
	return numOf(value), true
}

func (c Competition) prrTotal() (float64, bool) {
	prr, ok := c.Results["prr"].(map[string]any)
	if !ok {
		return 0, false
	}
	value, present := prr["total"]
	if !present || value == nil {
		return 0, false
	}
	return numOf(value), true
}

type Program struct {
	Meta         map[string]any
	Sessions     []Session
	Competitions []Competition
}

func (p Program) ProgramStart() string { return textOf(p.Meta["program_start"]) }

func textOf(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return typed
	}
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

func numOf(value any) float64 {
	switch typed := value.(type) {
	case nil:
		return 0
	case bool:
		if typed {
			return 1
		}
		return 0
	case float64:
		return typed
	case json.Number:
		parsed, _ := typed.Float64()
		return parsed
	case string:
		parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		if err != nil {
			return 0
		}
		return parsed
	}
	return 0
}

func present(value any) bool { return value != nil }

func singularize(word string) string {
	switch {
	case strings.HasSuffix(word, "sses"), strings.HasSuffix(word, "ches"), strings.HasSuffix(word, "shes"), strings.HasSuffix(word, "xes"):
		return word[:len(word)-2]
	case strings.HasSuffix(word, "s") && !strings.HasSuffix(word, "ss"):
		return word[:len(word)-1]
	}
	return word
}

func NormalizeName(name string) string {
	var stripped strings.Builder
	depth := 0
	for _, character := range name {
		switch {
		case character == '(':
			depth++
			stripped.WriteRune(' ')
		case character == ')' && depth > 0:
			depth--
		case depth == 0:
			stripped.WriteRune(character)
		}
	}
	words := strings.Fields(strings.ToLower(stripped.String()))
	for index, word := range words {
		words[index] = singularize(word)
	}
	return strings.Join(words, " ")
}

func sortCompetitionsDescending(competitions []Competition) []Competition {
	ordered := append([]Competition(nil), competitions...)
	sort.SliceStable(ordered, func(i, j int) bool { return ordered[i].DateText > ordered[j].DateText })
	return ordered
}
