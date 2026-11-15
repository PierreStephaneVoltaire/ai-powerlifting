package prompts

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
)

const maxPriorMuscles = 4

type Dims struct {
	Axial, Neural, Peripheral, Systemic float64
}

type ExerciseDose struct {
	Week           int
	Exercise       string
	Sets           float64
	Sessions       int
	IntensityPct   *float64
	RPE            *float64
	Reps, VolumeKg float64
}

type ExerciseInfo struct {
	Name           string
	Primary        []string
	Secondary      []string
	Fatigue        Dims
	Squat          float64
	Bench          float64
	Deadlift       float64
	TransferSource string
}

type MuscleDose struct {
	Week   int
	Muscle string
	Sets   float64
}

type MuscleLandmark struct {
	Muscle        string
	MEV, MAV, MRV float64
}

type FatigueWeek struct {
	Week  int
	Ratio Dims
}

type LiftSession struct {
	Date         string
	Lift         string
	E1rmKg       float64
	ResidualPct  *float64
	RPE          *float64
	Prior        Dims
	PriorMuscles map[string]float64
}

type ExercisePosition struct {
	Exercise, Lift                                    string
	Before, After, DayBefore1, DayBefore2, Outside48h int
	AvgDaysToNext                                     *float64
}

type table struct {
	Title  string
	Header []string
	Rows   [][]string
}

func plain(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func optional(value *float64, format string) string {
	if value == nil {
		return "-"
	}
	return fmt.Sprintf(format, *value)
}

func dims(value Dims) string {
	return fmt.Sprintf("%s/%s/%s/%s", plain(value.Axial), plain(value.Neural), plain(value.Peripheral), plain(value.Systemic))
}

func list(items []string) string {
	if len(items) == 0 {
		return "-"
	}
	return strings.Join(items, ", ")
}

func weekColumns(weeks map[int]bool) ([]int, []string) {
	ordered := make([]int, 0, len(weeks))
	for week := range weeks {
		ordered = append(ordered, week)
	}
	sort.Ints(ordered)
	header := make([]string, len(ordered))
	for index, week := range ordered {
		header[index] = fmt.Sprintf("W%d", week)
	}
	return ordered, header
}

func doseCell(dose ExerciseDose, ok bool) string {
	if !ok {
		return "-"
	}
	cell := fmt.Sprintf("%ss %dx", plain(dose.Sets), dose.Sessions)
	if dose.IntensityPct != nil {
		cell += fmt.Sprintf(" %s%%", plain(*dose.IntensityPct))
	}
	if dose.RPE != nil {
		cell += fmt.Sprintf(" @%s", plain(*dose.RPE))
	}
	return cell
}

func (in CorrelationInput) doseTable() table {
	weeks := map[int]bool{}
	doses := map[string]map[int]ExerciseDose{}
	totals := map[string]float64{}
	var order []string
	for _, dose := range in.ExerciseWeeks {
		weeks[dose.Week] = true
		if doses[dose.Exercise] == nil {
			doses[dose.Exercise] = map[int]ExerciseDose{}
			order = append(order, dose.Exercise)
		}
		doses[dose.Exercise][dose.Week] = dose
		totals[dose.Exercise] += dose.Sets
	}
	sort.SliceStable(order, func(i, j int) bool { return totals[order[i]] > totals[order[j]] })
	columns, header := weekColumns(weeks)
	result := table{Title: "Exercise Dose per Week (sets, sessions x, % of e1RM, @RPE)", Header: append([]string{"Exercise"}, header...)}
	for _, name := range order {
		row := []string{name}
		for _, week := range columns {
			dose, ok := doses[name][week]
			row = append(row, doseCell(dose, ok))
		}
		result.Rows = append(result.Rows, row)
	}
	return result
}

func (in CorrelationInput) profileTable() table {
	result := table{Title: "Exercise Profiles (fatigue axial/neural/peripheral/systemic, transfer to squat/bench/deadlift)", Header: []string{"Exercise", "Primary", "Secondary", "Fatigue", "Transfer", "Source"}}
	for _, info := range in.Exercises {
		transfer := fmt.Sprintf("%s/%s/%s", plain(info.Squat), plain(info.Bench), plain(info.Deadlift))
		result.Rows = append(result.Rows, []string{info.Name, list(info.Primary), list(info.Secondary), dims(info.Fatigue), transfer, info.TransferSource})
	}
	return result
}

func (in CorrelationInput) muscleTable() table {
	weeks := map[int]bool{}
	sets := map[string]map[int]float64{}
	for _, dose := range in.MuscleWeeks {
		weeks[dose.Week] = true
		if sets[dose.Muscle] == nil {
			sets[dose.Muscle] = map[int]float64{}
		}
		sets[dose.Muscle][dose.Week] += dose.Sets
	}
	landmarks := map[string]MuscleLandmark{}
	names := map[string]bool{}
	for _, landmark := range in.MuscleLandmarks {
		landmarks[landmark.Muscle] = landmark
		names[landmark.Muscle] = true
	}
	for name := range sets {
		names[name] = true
	}
	order := make([]string, 0, len(names))
	for name := range names {
		order = append(order, name)
	}
	sort.Strings(order)
	columns, header := weekColumns(weeks)
	result := table{Title: "Muscle Weekly Sets (primary 1.0, secondary 0.5) vs Landmarks", Header: append([]string{"Muscle", "MEV", "MAV", "MRV"}, header...)}
	for _, name := range order {
		landmark, rated := landmarks[name]
		row := []string{name, "-", "-", "-"}
		if rated {
			row = []string{name, plain(landmark.MEV), plain(landmark.MAV), plain(landmark.MRV)}
		}
		for _, week := range columns {
			if value, ok := sets[name][week]; ok {
				row = append(row, plain(value))
			} else {
				row = append(row, "0")
			}
		}
		result.Rows = append(result.Rows, row)
	}
	return result
}

func (in CorrelationInput) fatigueTable() table {
	result := table{Title: "Weekly Fatigue vs Typical Week (1.0 = typical)", Header: []string{"Week", "Axial", "Neural", "Peripheral", "Systemic"}}
	for _, week := range in.FatigueWeeks {
		ratio := week.Ratio
		result.Rows = append(result.Rows, []string{fmt.Sprintf("W%d", week.Week), plain(ratio.Axial), plain(ratio.Neural), plain(ratio.Peripheral), plain(ratio.Systemic)})
	}
	return result
}

func priorMuscles(sets map[string]float64) string {
	names := make([]string, 0, len(sets))
	for name := range sets {
		names = append(names, name)
	}
	sort.Slice(names, func(i, j int) bool {
		if sets[names[i]] != sets[names[j]] {
			return sets[names[i]] > sets[names[j]]
		}
		return names[i] < names[j]
	})
	names = names[:min(len(names), maxPriorMuscles)]
	parts := make([]string, len(names))
	for index, name := range names {
		parts[index] = fmt.Sprintf("%s %s", name, plain(sets[name]))
	}
	return list(parts)
}

func (in CorrelationInput) sessionTable() table {
	result := table{Title: "Main-Lift Sessions (e1RM vs trailing 3-session best; prior 48h load as ratio to typical day, axial/neural/peripheral/systemic)", Header: []string{"Date", "Lift", "e1RM", "vs best %", "RPE", "Prior 48h load", "Prior 48h muscle sets"}}
	for _, session := range in.LiftSessions {
		result.Rows = append(result.Rows, []string{session.Date, session.Lift, plain(session.E1rmKg), optional(session.ResidualPct, "%+.2f"), optional(session.RPE, "%.1f"), dims(session.Prior), priorMuscles(session.PriorMuscles)})
	}
	return result
}

func (in CorrelationInput) roiTable() table {
	result := table{Title: "Accessory Exercise ROI (pearson r between weekly volume and the lift's next-week e1RM change)", Header: []string{"Exercise", "Lift", "Pearson r", "Weeks"}}
	for _, row := range in.ExerciseROI {
		result.Rows = append(result.Rows, []string{row.Exercise, row.Lift, fmt.Sprintf("%+.3f", row.PearsonR), strconv.Itoa(row.WeeksObserved)})
	}
	return result
}

func (in CorrelationInput) positionTable() table {
	result := table{Title: "Accessory position relative to main lifts (sessions in the window; same session = accessory listed before or after the lift; day before = accessory session without the lift 1 or 2 days before a session of it; avg days to the lift's next session)", Header: []string{"Exercise", "Lift", "Same session before", "Same session after", "1 day before", "2 days before", "Outside 48h", "Avg days to next"}}
	for _, row := range in.Positions {
		result.Rows = append(result.Rows, []string{row.Exercise, row.Lift, strconv.Itoa(row.Before), strconv.Itoa(row.After), strconv.Itoa(row.DayBefore1), strconv.Itoa(row.DayBefore2), strconv.Itoa(row.Outside48h), optional(row.AvgDaysToNext, "%.1f")})
	}
	return result
}

func (in CorrelationInput) contextTables() []table {
	var tables []table
	for _, candidate := range []struct {
		present bool
		build   func() table
	}{
		{len(in.ExerciseROI) > 0, in.roiTable},
		{len(in.Positions) > 0, in.positionTable},
		{len(in.ExerciseWeeks) > 0, in.doseTable},
		{len(in.Exercises) > 0, in.profileTable},
		{len(in.MuscleWeeks) > 0 || len(in.MuscleLandmarks) > 0, in.muscleTable},
		{len(in.FatigueWeeks) > 0, in.fatigueTable},
		{len(in.LiftSessions) > 0, in.sessionTable},
	} {
		if candidate.present {
			tables = append(tables, candidate.build())
		}
	}
	return tables
}
