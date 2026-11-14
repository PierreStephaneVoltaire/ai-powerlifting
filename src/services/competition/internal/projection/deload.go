package projection

type weekLoad struct {
	week           int64
	isDeload       bool
	isBreak        bool
	effectiveIndex int
	hasEffective   bool
}

func (w weekLoad) excluded() bool { return w.isDeload || w.isBreak }

const (
	volumeThreshold       = 0.65
	volumeThresholdNoMain = 0.75
	rollingWindow         = 4
)

func inferProgramStart(sessions []Session) string {
	var earliest *Day
	for _, session := range sessions {
		if session.Date != nil && (earliest == nil || session.Date.Before(*earliest)) {
			day := *session.Date
			earliest = &day
		}
	}
	if earliest == nil {
		return ""
	}
	return earliest.Format("2006-01-02")
}

func bestPrimaryE1RM(sessions []Session) (float64, bool) {
	var best float64
	var found bool
	for _, session := range sessions {
		for _, exercise := range session.Exercises {
			if !isPrimary(exercise.Key) || exercise.FailedSets() > 0 || exercise.ExecutedSets() <= 0 {
				continue
			}
			if exercise.Kg <= 0 || exercise.RepsInt() <= 0 {
				continue
			}
			if value, ok := estimate(exercise.Kg, exercise.RepsInt(), session.SessionRPE); ok && (!found || value > best) {
				best, found = value, true
			}
		}
	}
	return best, found
}

func primaryRPEs(week []Session) []float64 {
	var rpes []float64
	for _, session := range week {
		hasPrimary := false
		for _, exercise := range session.Exercises {
			if isPrimary(exercise.Key) {
				hasPrimary = true
				break
			}
		}
		if !hasPrimary {
			continue
		}
		if session.SessionRPE != nil {
			rpes = append(rpes, *session.SessionRPE)
			continue
		}
		for _, exercise := range session.Exercises {
			if isPrimary(exercise.Key) && exercise.RPE != nil {
				rpes = append(rpes, *exercise.RPE)
			}
		}
	}
	return rpes
}

func detectWeekLoads(sessions []Session, programStart string) []weekLoad {
	if programStart == "" {
		programStart = inferProgramStart(sessions)
	}
	byWeek := map[int64][]Session{}
	lastWeek := int64(1)
	for _, session := range sessions {
		week, ok := session.Week(programStart)
		if !ok {
			continue
		}
		lastWeek = max(lastWeek, week)
		if session.Completed {
			byWeek[week] = append(byWeek[week], session)
		}
	}
	var results []weekLoad
	var previousVolumes, previousE1RMs []float64
	for week := int64(1); week <= lastWeek; week++ {
		members := byWeek[week]
		volume := 0.0
		hasMain := false
		for _, session := range members {
			for _, exercise := range session.Exercises {
				volume += exercise.ExecutedVolume()
				if isPrimary(exercise.Key) && exercise.ExecutedSets() > 0 {
					hasMain = true
				}
			}
		}
		isBreak := volume == 0
		isDeload := false
		if !isBreak && len(previousVolumes) > 0 {
			from := max(len(previousVolumes)-rollingWindow, 0)
			center := median(previousVolumes[from:])
			threshold := volumeThresholdNoMain
			if hasMain {
				threshold = volumeThreshold
			}
			if center > 0 && volume < threshold*center {
				isDeload = deloadVerdict(members, hasMain, previousE1RMs)
			}
		}
		bestE1RM, hasE1RM := bestPrimaryE1RM(members)
		results = append(results, weekLoad{week: week, isDeload: isDeload, isBreak: isBreak})
		if !isDeload && !isBreak {
			previousVolumes = append(previousVolumes, volume)
			if hasE1RM {
				previousE1RMs = append(previousE1RMs, bestE1RM)
			}
		}
	}
	effective := 0
	for index := range results {
		if !results[index].excluded() {
			results[index].effectiveIndex, results[index].hasEffective = effective, true
			effective++
		}
	}
	return results
}

func deloadVerdict(members []Session, hasMain bool, previousE1RMs []float64) bool {
	if !hasMain {
		return true
	}
	rpes := primaryRPEs(members)
	if len(rpes) > 0 {
		for _, rpe := range rpes {
			if rpe > 6 {
				return false
			}
		}
		return true
	}
	best, ok := bestPrimaryE1RM(members)
	if !ok || len(previousE1RMs) == 0 {
		return false
	}
	tail := previousE1RMs[max(len(previousE1RMs)-2, 0):]
	reference := tail[0]
	for _, value := range tail[1:] {
		reference = max(reference, value)
	}
	return best < reference*0.90
}
