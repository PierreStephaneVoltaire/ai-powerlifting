package projection

import (
	"math"
	"sort"
	"time"
)

const lookbackDays = 90

type progression struct {
	slope      float64
	fitQuality float64
}

func progressionRate(sessions []Session, exercise, programStart string, reference Day) (progression, bool) {
	if programStart == "" {
		programStart = inferProgramStart(sessions)
	}
	name := NormalizeName(exercise)
	cutoff := reference.Add(-lookbackDays * 24 * time.Hour)
	effective := map[int64]int{}
	for _, load := range detectWeekLoads(sessions, programStart) {
		if load.hasEffective {
			effective[load.week] = load.effectiveIndex
		}
	}
	byWeek := map[int][]float64{}
	for _, session := range sessions {
		if !session.Completed || !hasExercise(session, name) {
			continue
		}
		if session.Date == nil || session.Date.Before(cutoff) || session.Date.After(reference) {
			continue
		}
		week, ok := session.Week(programStart)
		if !ok {
			continue
		}
		index, ok := effective[week]
		if !ok {
			continue
		}
		for _, item := range session.Exercises {
			if item.Key != name || item.FailedSets() > 0 || item.ExecutedSets() <= 0 || item.Kg <= 0 || item.RepsInt() <= 0 {
				continue
			}
			if value, ok := estimate(item.Kg, item.RepsInt(), session.SessionRPE); ok {
				byWeek[index] = append(byWeek[index], value)
			}
		}
	}
	if len(byWeek) < 2 {
		return progression{}, false
	}
	keys := make([]int, 0, len(byWeek))
	for key := range byWeek {
		keys = append(keys, key)
	}
	sort.Ints(keys)
	xs := make([]float64, len(keys))
	ys := make([]float64, len(keys))
	for index, key := range keys {
		xs[index] = float64(key)
		best := -math.MaxFloat64
		for _, value := range byWeek[key] {
			best = math.Max(best, value)
		}
		ys[index] = best
	}
	line := theilSen(ys, xs)
	return progression{slope: round(line.slope, 2), fitQuality: fitQuality(xs, ys, line)}, true
}

func hasExercise(session Session, name string) bool {
	for _, exercise := range session.Exercises {
		if exercise.Key == name {
			return true
		}
	}
	return false
}
