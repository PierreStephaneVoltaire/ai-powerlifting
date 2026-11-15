package projection

import (
	"math"
	"strings"
)

const (
	minMultiplier       = 0.92
	maxMultiplier       = 1.05
	minCalibratedMeets  = 2
	calibrationMeetsCap = 3
)

type Calibration struct {
	Calibrated       bool
	Meets            int
	MedianPRR        *float64
	LambdaMultiplier *float64
}

func calibrate(competitions []Competition, reference Day) Calibration {
	var totals []float64
	for _, competition := range sortCompetitionsDescending(competitions) {
		if competition.Date == nil || competition.Date.After(reference) || competition.Status != "completed" {
			continue
		}
		if total, ok := competition.prrTotal(); ok && total > 0 {
			totals = append(totals, total)
		}
	}
	result := Calibration{Meets: len(totals)}
	if len(totals) == 0 {
		return result
	}
	value := round(median(totals[:min(len(totals), calibrationMeetsCap)]), 3)
	result.MedianPRR = &value
	result.Calibrated = len(totals) >= minCalibratedMeets
	if result.Calibrated {
		multiplier := round(clamp(value, minMultiplier, maxMultiplier), 3)
		result.LambdaMultiplier = &multiplier
	}
	return result
}

type LiftProjection struct {
	Current    float64
	Projected  float64
	Slope      float64
	Confidence float64
	Clamped    bool
}

type Projection struct {
	Total       float64
	Confidence  float64
	WeeksToComp float64
	Lifts       map[string]LiftProjection
	Calibration Calibration
}

func currentWeek(programStart string, sessions []Session, today Day) int64 {
	if len(sessions) > 0 {
		var started []int64
		var all []int64
		for _, session := range sessions {
			if session.WeekNumber == nil {
				continue
			}
			all = append(all, *session.WeekNumber)
			if session.Completed || (session.Date != nil && !session.Date.After(today)) {
				started = append(started, *session.WeekNumber)
			}
		}
		if len(started) > 0 {
			return maxOf(started)
		}
		if len(all) > 0 {
			return minOf(all)
		}
	}
	start, ok := ParseDay(programStart)
	if !ok {
		return 1
	}
	return max(floorDiv(daysBetween(today, start), 7)+1, 1)
}

func maxOf(values []int64) int64 {
	best := values[0]
	for _, value := range values[1:] {
		best = max(best, value)
	}
	return best
}

func minOf(values []int64) int64 {
	best := values[0]
	for _, value := range values[1:] {
		best = min(best, value)
	}
	return best
}

func firstNumber(meta map[string]any, keys ...string) float64 {
	for _, key := range keys {
		if value, present := meta[key]; present {
			return numOf(value)
		}
	}
	return 0
}

func dots(total, bodyweight float64, sex string) (float64, bool) {
	coefficients, ok := dotsFor(sex)
	if !ok {
		return 0, false
	}
	if math.IsNaN(total) || math.IsInf(total, 0) || math.IsNaN(bodyweight) || math.IsInf(bodyweight, 0) || total < 0 || bodyweight <= 0 {
		return 0, false
	}
	denominator := coefficients.A + coefficients.B*bodyweight + coefficients.C*math.Pow(bodyweight, 2) + coefficients.D*math.Pow(bodyweight, 3) + coefficients.E*math.Pow(bodyweight, 4)
	if math.Abs(denominator) >= 1e-12 {
		return round(500*total/denominator, 2), true
	}
	return 0, true
}

func Meet(program Program, compDate string, reference, today Day) (*Projection, string) {
	if compDate == "" {
		return nil, "No competition date set"
	}
	comp, ok := ParseDay(compDate)
	if !ok {
		return nil, "Invalid competition date: " + compDate
	}
	if !comp.After(reference) {
		return nil, "Competition date is in the past"
	}
	weeksToComp := float64(daysBetween(comp, reference)) / 7.0
	sessions := program.Sessions
	programStart := program.ProgramStart()
	if programStart == "" {
		programStart = inferProgramStart(sessions)
	}
	maxes := maxesFromCompetitions(program.Competitions, reference)
	if maxes.Empty() {
		maxes = maxesFromSessions(sessions, 42, reference)
	}
	if maxes.Empty() {
		return nil, "No session data to estimate maxes from"
	}
	calibration := calibrate(program.Competitions, reference)
	bodyweight := firstNumber(program.Meta, "current_body_weight_kg", "bodyweight_kg")
	sex := "male"
	if value, present := program.Meta["sex"]; present {
		sex, _ = value.(string)
		sex = strings.ToLower(sex)
	}
	totalNow := 0.0
	for _, lift := range lifts {
		value, _ := maxes.Get(lift)
		totalNow += value
	}
	dotsNow := 0.0
	if bodyweight > 0 && totalNow > 0 {
		dotsNow, _ = dots(totalNow, bodyweight, sex)
	}
	baseLambda, peakFactor := 0.90, 1.03
	switch {
	case dotsNow >= 400:
		baseLambda, peakFactor = 0.85, 1.05
	case dotsNow < 300:
		baseLambda, peakFactor = 0.96, 1.01
	}
	lambda := baseLambda
	if calibration.LambdaMultiplier != nil {
		lambda = math.Min(baseLambda**calibration.LambdaMultiplier, 0.995)
	}
	taper := 1.0
	switch {
	case weeksToComp >= 12:
		taper = 3
	case weeksToComp >= 8:
		taper = 2
	}
	weekNow := currentWeek(programStart, sessions, today)
	compWeek := float64(weekNow) + weeksToComp
	remaining := 0.0
	for _, load := range detectWeekLoads(sessions, programStart) {
		if load.isDeload && weekNow <= load.week && float64(load.week) <= compWeek {
			remaining++
		}
	}
	plannedDeloads := remaining
	if remaining == 0 && weeksToComp > 4 {
		plannedDeloads = math.Floor(weeksToComp / 4)
	}
	nT := math.Max(weeksToComp-taper-plannedDeloads, 0)
	ceilingPct := math.Min(0.20, 0.10+0.005*math.Max(weeksToComp-8, 0))

	projection := &Projection{Lifts: map[string]LiftProjection{}, Calibration: calibration}
	hasProgression := false
	for _, lift := range lifts {
		current, ok := maxes.Get(lift)
		if !ok {
			continue
		}
		slope, fitValue := 0.0, 0.0
		if result, ok := progressionRate(sessions, lift, program.Glossary, programStart, reference); ok {
			hasProgression = true
			slope, fitValue = result.slope, result.fitQuality
		}
		lambda = math.Min(lambda, 0.995)
		gain := 0.0
		if nT > 0 && slope > 0 {
			if lambda < 0.999999 {
				gain = slope * lambda * (1 - math.Pow(lambda, nT)) / (1 - lambda)
			} else {
				gain = slope * nT
			}
		}
		projected := (current + gain) * peakFactor
		ceiling := current * (1 + ceilingPct)
		clamped := projected > ceiling
		projected = math.Max(current, math.Min(projected, ceiling))
		projection.Lifts[lift.Key()] = LiftProjection{
			Current:    round(current, 1),
			Projected:  round(projected, 1),
			Slope:      slope,
			Confidence: round(clamp(fitValue, 0, 1), 2),
			Clamped:    clamped,
		}
	}
	if len(projection.Lifts) == 0 {
		return nil, "No lift maxes found (squat, bench, deadlift)"
	}
	if !hasProgression {
		return nil, "Insufficient session data to estimate progression"
	}
	total, confidence := 0.0, 0.0
	for _, key := range []string{"bench", "deadlift", "squat"} {
		if value, ok := projection.Lifts[key]; ok {
			total += value.Projected
			confidence += value.Confidence
		}
	}
	projection.Total = round(total, 1)
	projection.Confidence = round(confidence/float64(len(projection.Lifts)), 2)
	projection.WeeksToComp = round(weeksToComp, 1)
	return projection, ""
}
