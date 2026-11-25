package profile

import (
	"math"
	"strings"
)

var muscles = map[string]bool{}
var muscleSeparators = strings.NewReplacer("-", "_", " ", "_")

var muscleAliases = map[string]string{
	"front_deltoids": "front_delts", "lateral_delts": "side_delts", "rear_deltoids": "rear_delts",
	"adductor": "adductors", "serratus_anterior": "serratus",
}

var bodyFatLabels = map[string]string{
	"under_10": "Under 10%", "10_15": "10 to 15%", "15_20": "15 to 20%",
	"20_25": "20 to 25%", "25_30": "25 to 30%", "over_30": "Over 30%",
}

func Athlete(meta map[string]any) map[string]any {
	fields := map[string]string{"bodyweight_kg": "current_body_weight_kg", "height_cm": "height_cm", "arm_wingspan_cm": "arm_wingspan_cm", "leg_length_cm": "leg_length_cm", "sex": "sex"}
	result := map[string]any{}
	for output, input := range fields {
		value := meta[input]
		switch value := value.(type) {
		case nil:
			continue
		case string:
			if value == "" {
				continue
			}
		case float64:
			if value == 0 {
				continue
			}
		case int:
			if value == 0 {
				continue
			}
		}
		result[output] = value
	}
	if label := bodyFatLabels[stringValue(meta["body_fat_range"])]; label != "" {
		result["body_fat_range"] = label
	}
	return result
}

func stringValue(value any) string {
	result, _ := value.(string)
	return result
}

func init() {
	for _, name := range strings.Fields("quads hamstrings glutes calves tibialis_anterior hip_flexors adductors chest triceps front_delts side_delts rear_delts lats traps rhomboids teres_major biceps forearms erectors lower_back core obliques serratus") {
		muscles[name] = true
	}
}

func MuscleGroups(buckets ...[]string) [][]string {
	limits := []int{4, 5, 5}
	seen := map[string]bool{}
	result := make([][]string, len(buckets))
	for i, bucket := range buckets {
		result[i] = []string{}
		limit := 5
		if i < len(limits) {
			limit = limits[i]
		}
		for _, raw := range bucket {
			name := muscleSeparators.Replace(strings.ToLower(strings.TrimSpace(raw)))
			if alias, ok := muscleAliases[name]; ok {
				name = alias
			}
			if !muscles[name] || seen[name] {
				continue
			}
			seen[name] = true
			result[i] = append(result[i], name)
			if len(result[i]) == limit {
				break
			}
		}
	}
	return result
}

func Stimulus(value float64) float64 {
	value = math.RoundToEven(value/0.05) * 0.05
	return math.Max(1, math.Min(2, math.RoundToEven(value*100)/100))
}

func RelatedLifts(name, category string) []string {
	name, category = strings.ToLower(strings.TrimSpace(name)), strings.ToLower(strings.TrimSpace(category))
	result := []string{}
	if category == "squat" || strings.Contains(name, "squat") {
		result = append(result, "squat")
	}
	if category == "bench" || strings.Contains(name, "bench") {
		result = append(result, "bench")
	}
	if category == "deadlift" || strings.Contains(name, "deadlift") || strings.Contains(name, "rdl") || strings.Contains(name, "romanian") || strings.Contains(name, "stiff leg") || strings.Contains(name, "stiff-leg") {
		result = append(result, "deadlift")
	}
	return result
}

func SelectProfiles(name, category string, profiles []map[string]any) ([]string, []map[string]any) {
	byLift := map[string]map[string]any{}
	for _, item := range profiles {
		lift, _ := item["lift"].(string)
		lift = strings.ToLower(strings.TrimSpace(lift))
		if lift == "squat" || lift == "bench" || lift == "deadlift" {
			byLift[lift] = item
		}
	}
	if len(byLift) == 0 {
		return []string{}, []map[string]any{}
	}
	related := RelatedLifts(name, category)
	order := append([]string{}, related...)
	for _, lift := range []string{"squat", "bench", "deadlift"} {
		found := false
		for _, selected := range related {
			if selected == lift {
				found = true
				break
			}
		}
		if !found {
			order = append(order, lift)
		}
	}
	result := []map[string]any{}
	for _, lift := range order {
		if item := byLift[lift]; item != nil {
			result = append(result, item)
		}
	}
	return related, result
}
