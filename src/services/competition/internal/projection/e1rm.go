package projection

import (
	"math"
	"sort"
	"time"
)

func estimate(weight float64, reps int, rpe *float64) (float64, bool) {
	if math.IsNaN(weight) || math.IsInf(weight, 0) || weight <= 0 {
		return 0, false
	}
	var percent float64
	var found bool
	switch {
	case rpe != nil && reps >= 1 && reps <= 10 && *rpe >= 6 && *rpe <= 10:
		percent, found = rpePercent(reps, int(*rpe))
	case rpe == nil && reps >= 1 && reps <= 10:
		percent, found = rpePercent(reps, 10)
	}
	if !found || percent == 0 {
		return 0, false
	}
	return weight / percent, true
}

func maxesFromCompetitions(competitions []Competition, reference Day) Maxes {
	for _, competition := range sortCompetitionsDescending(competitions) {
		if competition.Status == "skipped" || competition.Date == nil || competition.Date.After(reference) {
			continue
		}
		if len(competition.Results) == 0 {
			continue
		}
		var best Maxes
		for _, lift := range lifts {
			if value, ok := competition.resultKg(lift.Key() + "_kg"); ok {
				best.Set(lift, value)
			}
		}
		if !best.Empty() {
			return best
		}
	}
	return Maxes{}
}

func maxesFromSessions(sessions []Session, lookbackDays int, reference Day) Maxes {
	cutoff := reference.Add(-time.Duration(lookbackDays) * 24 * time.Hour)
	var estimates [3][]float64
	for _, session := range sessions {
		if session.Date == nil || session.Date.Before(cutoff) || session.Date.After(reference) {
			continue
		}
		if session.Status == "planned" || session.Status == "skipped" {
			continue
		}
		for _, exercise := range session.Exercises {
			if exercise.FailedSets() > 0 || exercise.ExecutedSets() <= 0 {
				continue
			}
			reps := exercise.RepsInt()
			if exercise.Kg <= 0 || reps <= 0 {
				continue
			}
			lift, ok := liftFromName(exercise.Key)
			if !ok {
				continue
			}
			if value, ok := estimate(exercise.Kg, reps, session.SessionRPE); ok {
				estimates[lift] = append(estimates[lift], value)
			}
		}
	}
	var maxes Maxes
	found := 0
	for _, lift := range lifts {
		values := estimates[lift]
		if len(values) >= 3 {
			sort.Float64s(values)
			index := min(int(float64(len(values))*0.9), len(values)-1)
			maxes.Set(lift, values[index])
			found++
		}
	}
	if found >= 2 {
		return maxes
	}
	return Maxes{}
}
