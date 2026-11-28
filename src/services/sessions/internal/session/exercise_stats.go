package session

import (
	"context"
	"encoding/json"
	"math"
	"math/big"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"powerlifting/sessions/internal/apperr"
	"powerlifting/sessions/internal/value"
)

var exerciseParenPattern = regexp.MustCompile(`\s*\(.*?\)\s*`)

func singularizeWord(word string) string {
	if strings.HasSuffix(word, "sses") || strings.HasSuffix(word, "ches") || strings.HasSuffix(word, "shes") || strings.HasSuffix(word, "xes") {
		return word[:len(word)-2]
	}
	if strings.HasSuffix(word, "s") && !strings.HasSuffix(word, "ss") {
		return word[:len(word)-1]
	}
	return word
}

func normalizeExerciseName(name string) string {
	stripped := strings.TrimSpace(exerciseParenPattern.ReplaceAllString(name, " "))
	if stripped == "" {
		return ""
	}
	words := strings.Fields(strings.ToLower(stripped))
	for i, word := range words {
		words[i] = singularizeWord(word)
	}
	return strings.Join(words, " ")
}

type performedSet struct {
	repsVal  any
	repsText string
	kgVal    any
	kgText   string
	status   string
	timed    bool
}

func sanitizeNumber(v any) (json.Number, string, bool) {
	switch typed := v.(type) {
	case value.Decimal:
		if _, ok := new(big.Rat).SetString(string(typed)); !ok {
			return "", "", false
		}
		n := value.Sanitized(typed)
		return n, string(n), true
	case json.Number:
		if _, ok := new(big.Rat).SetString(string(typed)); !ok {
			return "", "", false
		}
		n := value.Sanitized(value.Decimal(typed))
		return n, string(n), true
	case int:
		n := value.Int(typed)
		return n, string(n), true
	case int64:
		n := json.Number(strconv.FormatInt(typed, 10))
		return n, string(n), true
	case float64:
		if math.IsNaN(typed) || math.IsInf(typed, 0) {
			return "", "", false
		}
		n := value.Sanitized(value.Decimal(strconv.FormatFloat(typed, 'g', -1, 64)))
		return n, string(n), true
	}
	return "", "", false
}

func extractPerformedSets(item value.Item, targetNormalized string) []performedSet {
	if targetNormalized == "" {
		return nil
	}
	exercises, _ := item["exercises"].([]any)
	sessionCompleted := value.Truthy(item["completed"])
	var out []performedSet
	for _, entry := range exercises {
		exercise, ok := value.Map(entry)
		if !ok {
			continue
		}
		exName, _ := exercise["name"].(string)
		if normalizeExerciseName(exName) != targetNormalized {
			continue
		}
		setsData, _ := exercise["sets_data"].([]any)
		count := len(setsData)
		if count == 0 {
			count = value.IntOf(exercise["sets"], 0)
		}
		statuses, _ := exercise["set_statuses"].([]any)
		repUnit, _ := exercise["rep_unit"].(string)
		timed := (repUnit != "" && repUnit != "reps") || exercise["duration_minutes"] != nil
		for i := 0; i < count; i++ {
			status := "pending"
			if i < len(statuses) {
				if s, ok := statuses[i].(string); ok && s != "" {
					status = s
				} else if sessionCompleted {
					status = "completed"
				}
			} else if sessionCompleted {
				status = "completed"
			}
			if status != "completed" && status != "failed" {
				continue
			}
			var rawReps, rawKg any
			if i < len(setsData) {
				if sm, ok := value.Map(setsData[i]); ok {
					rawReps = sm["reps"]
					rawKg = sm["kg"]
				}
			} else {
				rawReps = exercise["reps"]
				rawKg = exercise["kg"]
			}
			var repsVal any
			repsNum, repsText, hasReps := sanitizeNumber(rawReps)
			if hasReps {
				repsVal = repsNum
			}
			var kgVal any
			kgNum, kgText, hasKg := sanitizeNumber(rawKg)
			if hasKg {
				kgVal = kgNum
			}
			out = append(out, performedSet{
				repsVal:  repsVal,
				repsText: repsText,
				kgVal:    kgVal,
				kgText:   kgText,
				status:   status,
				timed:    timed,
			})
		}
	}
	return out
}

type historyKey struct {
	reps   string
	kg     string
	status string
}

type historyGroup struct {
	sets   int
	reps   any
	kg     any
	status string
}

type prBest struct {
	set   bool
	kg    float64
	kgVal any
	date  string
}

func (s *Service) ExerciseHistory(ctx context.Context, pk, exerciseName, excludeSessionID string) (value.Item, error) {
	programSK, err := s.Programs.CurrentSK(ctx, pk)
	if err != nil {
		return nil, err
	}
	if programSK == "" {
		return nil, apperr.NotFound("Program not found")
	}
	items, err := s.Sessions.CurrentBlockExercises(ctx, pk, programSK)
	if err != nil {
		return nil, err
	}
	slices.SortStableFunc(items, func(a, b value.Item) int {
		dateA, _ := a["date"].(string)
		dateB, _ := b["date"].(string)
		return strings.Compare(dateB, dateA)
	})
	target := normalizeExerciseName(exerciseName)
	entries := []any{}
	for _, item := range items {
		if excludeSessionID != "" && rawIdentity(item) == excludeSessionID {
			continue
		}
		sets := extractPerformedSets(item, target)
		if len(sets) == 0 {
			continue
		}
		date, _ := item["date"].(string)
		var groups []*historyGroup
		seen := map[historyKey]int{}
		for _, set := range sets {
			key := historyKey{reps: set.repsText, kg: set.kgText, status: set.status}
			if idx, ok := seen[key]; ok {
				groups[idx].sets++
			} else {
				seen[key] = len(groups)
				groups = append(groups, &historyGroup{
					sets:   1,
					reps:   set.repsVal,
					kg:     set.kgVal,
					status: set.status,
				})
			}
		}
		for _, group := range groups {
			entries = append(entries, value.Item{
				"date":   date,
				"sets":   value.Int(group.sets),
				"reps":   group.reps,
				"kg":     group.kg,
				"status": group.status,
			})
		}
	}
	return value.Item{"entries": entries}, nil
}

func (s *Service) ExercisePRs(ctx context.Context, pk, exerciseName string) (value.Item, error) {
	programSK, err := s.Programs.CurrentSK(ctx, pk)
	if err != nil {
		return nil, err
	}
	if programSK == "" {
		return nil, apperr.NotFound("Program not found")
	}
	items, err := s.Sessions.CurrentBlockExercises(ctx, pk, programSK)
	if err != nil {
		return nil, err
	}
	target := normalizeExerciseName(exerciseName)
	var best [13]prBest
	for _, item := range items {
		date, _ := item["date"].(string)
		for _, set := range extractPerformedSets(item, target) {
			if set.timed || set.status != "completed" {
				continue
			}
			reps, err := strconv.Atoi(set.repsText)
			if err != nil || reps < 1 || reps > 12 {
				continue
			}
			kg, err := strconv.ParseFloat(set.kgText, 64)
			if err != nil || kg <= 0 || math.IsNaN(kg) || math.IsInf(kg, 0) {
				continue
			}
			cur := best[reps]
			if !cur.set || kg > cur.kg || (kg == cur.kg && date > cur.date) {
				best[reps] = prBest{set: true, kg: kg, kgVal: set.kgVal, date: date}
			}
		}
	}
	records := make([]any, 0, 12)
	for r := 1; r <= 12; r++ {
		if best[r].set {
			records = append(records, value.Item{
				"reps": value.Int(r),
				"kg":   best[r].kgVal,
				"date": best[r].date,
			})
		}
	}
	return value.Item{"records": records}, nil
}
