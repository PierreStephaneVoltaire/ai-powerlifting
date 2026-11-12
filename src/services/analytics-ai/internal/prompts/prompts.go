package prompts

import (
	"bytes"
	"embed"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"text/template"
	"unicode"

	"powerlifting/analytics-ai/internal/pyjson"
)

//go:embed templates/*.tmpl
var templateFiles embed.FS

//go:embed tools/*.json
var toolFiles embed.FS

var templates = template.Must(template.ParseFS(templateFiles, "templates/*.tmpl"))

func system(name string) string {
	var out bytes.Buffer
	if err := templates.ExecuteTemplate(&out, name+".tmpl", nil); err != nil {
		panic(err)
	}
	return strings.TrimSpace(out.String())
}

func CorrelationSystem() string       { return system("correlation_system") }
func ProgramEvaluationSystem() string { return system("program_evaluation_system") }
func MultiBlockSystem() string        { return system("multi_block_comparison_system") }

func Tool(name string) map[string]any {
	raw, err := toolFiles.ReadFile("tools/" + name + ".json")
	if err != nil {
		panic(err)
	}
	value, err := pyjson.Decode(raw)
	if err != nil {
		panic(err)
	}
	return value.(map[string]any)
}

type LiftProfile struct {
	Lift            string
	StyleNotes      string
	StickingPoints  string
	PrimaryMuscle   string
	VolumeTolerance string
}

type Measurement struct {
	Name  string
	Value *float64
}

type BodyweightTrend struct {
	Latest    *float64
	Direction string
	Change    *float64
}

type WeekLifts struct {
	Week                   int
	Squat, Bench, Deadlift *float64
}

type Exercise struct {
	Name     string
	VolumeKg float64
}

type WeekAccessory struct {
	Week      int
	Exercises []Exercise
}

type ROIRow struct {
	Exercise      string
	PearsonR      float64
	WeeksObserved int
}

type CorrelationInput struct {
	Weeks              int
	WindowStart        string
	WeeksToPrimaryComp *float64
	LiftProfiles       []LiftProfile
	Measurements       []Measurement
	CaloricStatus      string
	Bodyweight         *BodyweightTrend
	E1rm               []WeekLifts
	Accessory          []WeekAccessory
	ExerciseROI        []ROIRow
}

type e1rmRow struct {
	Week                   int
	Squat, Bench, Deadlift string
}

type accessoryRow struct {
	Week  int
	Cells []string
}

type roiRow struct {
	Exercise string
	PearsonR string
	Weeks    int
}

type measurementLine struct {
	Name  string
	Value string
}

type profileView struct {
	Lift, StyleNotes, StickingPoints, PrimaryMuscle, VolumeTolerance string
}

type correlationView struct {
	Weeks            int
	WindowStart      string
	PrimaryWeeks     string
	Profiles         []profileView
	ShowMeasurements bool
	Measurements     []measurementLine
	CaloricStatus    string
	BodyweightLine   string
	E1rmRows         []e1rmRow
	Accessory        []string
	AccessoryRows    []accessoryRow
	ROI              []roiRow
}

func Title(text string) string {
	var out strings.Builder
	boundary := true
	for _, r := range text {
		switch {
		case !unicode.IsLetter(r):
			boundary = true
			out.WriteRune(r)
		case boundary:
			out.WriteRune(unicode.ToUpper(r))
			boundary = false
		default:
			out.WriteRune(unicode.ToLower(r))
		}
	}
	return out.String()
}

func number(value float64) string {
	if value == float64(int64(value)) && value < 1e15 && value > -1e15 {
		return strconv.FormatInt(int64(value), 10)
	}
	return pyjson.Float(value)
}

func fixed(format string, value *float64) string {
	if value == nil || *value == 0 {
		return "-"
	}
	return fmt.Sprintf(format, *value)
}

func (in CorrelationInput) view() correlationView {
	view := correlationView{Weeks: in.Weeks, WindowStart: in.WindowStart, CaloricStatus: in.CaloricStatus}
	if in.WeeksToPrimaryComp != nil {
		view.PrimaryWeeks = fmt.Sprintf("%.1f", *in.WeeksToPrimaryComp)
	}
	for _, profile := range in.LiftProfiles {
		lift := profile.Lift
		if lift == "" {
			lift = "?"
		}
		view.Profiles = append(view.Profiles, profileView{Title(lift), profile.StyleNotes, profile.StickingPoints, profile.PrimaryMuscle, profile.VolumeTolerance})
	}
	for _, measurement := range in.Measurements {
		if measurement.Value == nil {
			continue
		}
		if *measurement.Value != 0 {
			view.ShowMeasurements = true
		}
		view.Measurements = append(view.Measurements, measurementLine{strings.ReplaceAll(measurement.Name, "_", " "), number(*measurement.Value)})
	}
	if !view.ShowMeasurements {
		view.Measurements = nil
	}
	view.BodyweightLine = bodyweightLine(in.Bodyweight)
	weekSet := map[int]bool{}
	for _, row := range in.E1rm {
		weekSet[row.Week] = true
	}
	volumes := map[int]map[string]float64{}
	totals := map[string]float64{}
	var order []string
	for _, week := range in.Accessory {
		volumes[week.Week] = map[string]float64{}
		for _, exercise := range week.Exercises {
			volumes[week.Week][exercise.Name] += exercise.VolumeKg
			if _, seen := totals[exercise.Name]; !seen {
				order = append(order, exercise.Name)
			}
			totals[exercise.Name] += exercise.VolumeKg
		}
		weekSet[week.Week] = true
	}
	sort.SliceStable(order, func(i, j int) bool { return totals[order[i]] > totals[order[j]] })
	order = order[:min(len(order), 20)]
	weeks := make([]int, 0, len(weekSet))
	for week := range weekSet {
		weeks = append(weeks, week)
	}
	sort.Ints(weeks)
	lifts := map[int]WeekLifts{}
	for _, row := range in.E1rm {
		lifts[row.Week] = row
	}
	for _, week := range weeks {
		row := lifts[week]
		view.E1rmRows = append(view.E1rmRows, e1rmRow{week, fixed("%.1f", row.Squat), fixed("%.1f", row.Bench), fixed("%.1f", row.Deadlift)})
	}
	view.Accessory = order
	for _, week := range weeks {
		cells := make([]string, 0, len(order))
		for _, name := range order {
			volume := volumes[week][name]
			cells = append(cells, fixed("%.0f", &volume))
		}
		view.AccessoryRows = append(view.AccessoryRows, accessoryRow{week, cells})
	}
	for _, row := range in.ExerciseROI {
		name := row.Exercise
		if name == "" {
			name = "?"
		}
		view.ROI = append(view.ROI, roiRow{name, fmt.Sprintf("%+.3f", row.PearsonR), row.WeeksObserved})
	}
	return view
}

func bodyweightLine(trend *BodyweightTrend) string {
	if trend == nil || trend.Latest == nil {
		return ""
	}
	direction := trend.Direction
	if direction == "" {
		direction = "unclear"
	}
	line := fmt.Sprintf("**Body weight trend:** %s kg, %s", number(*trend.Latest), direction)
	if trend.Change != nil {
		sign := ""
		if *trend.Change > 0 {
			sign = "+"
		}
		line += fmt.Sprintf(" (%s%s kg over window)", sign, number(*trend.Change))
	}
	return line
}

func RenderCorrelationUser(input CorrelationInput) (string, error) {
	var out bytes.Buffer
	if err := templates.ExecuteTemplate(&out, "correlation_user.tmpl", input.view()); err != nil {
		return "", err
	}
	return out.String(), nil
}
