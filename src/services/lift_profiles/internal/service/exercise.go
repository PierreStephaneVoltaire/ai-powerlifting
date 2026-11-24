package service

import (
	"context"
	_ "embed"
	"fmt"
	"math"
	"strings"

	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
)

//go:embed fatigue_prompt.txt
var fatiguePrompt string

//go:embed muscle_prompt.txt
var musclePrompt string

var allowedMuscles = strings.Fields("quads hamstrings glutes calves tibialis_anterior hip_flexors adductors chest triceps front_delts side_delts rear_delts lats traps rhomboids teres_major biceps forearms erectors lower_back core obliques serratus")

func exerciseMessage(defs profile.Definitions, exercise, program map[string]any, profiles []map[string]any, muscle bool) string {
	name, _ := exercise["name"].(string)
	if name == "" {
		name = "Unknown"
	}
	lines := []string{"Exercise: " + name}
	for _, field := range []struct{ key, label string }{{"category", "Category"}, {"equipment", "Equipment"}, {"primary_muscles", "Primary muscles"}, {"secondary_muscles", "Secondary muscles"}, {"tertiary_muscles", "Tertiary muscles"}, {"description", "Description"}, {"how_to_perform", "How performed"}, {"why_do_it", "Training purpose"}} {
		value := exercise[field.key]
		if list, ok := value.([]any); ok {
			items := []string{}
			for _, item := range list {
				if text, ok := item.(string); ok {
					items = append(items, text)
				}
			}
			if len(items) != 0 {
				label := field.label
				if muscle {
					label = "Existing " + strings.ToLower(label)
				}
				lines = append(lines, label+": "+strings.Join(items, ", "))
			}
		} else if text, ok := value.(string); ok && text != "" {
			lines = append(lines, field.label+": "+text)
		}
	}
	meta, _ := program["meta"].(map[string]any)
	metrics := profile.Athlete(meta)
	if len(metrics) > 0 {
		lines = append(lines, "", "Athlete metrics:")
		for _, key := range []string{"bodyweight_kg", "height_cm", "arm_wingspan_cm", "leg_length_cm", "body_fat_range", "sex"} {
			if value, ok := metrics[key]; ok {
				lines = append(lines, fmt.Sprintf("  %s: %v", key, value))
			}
		}
	}
	category, _ := exercise["category"].(string)
	category = strings.ToLower(strings.TrimSpace(category))
	selected := profiles
	if muscle {
		related, chosen := profile.SelectProfiles(name, category, profiles)
		selected = chosen
		if len(chosen) > 0 {
			lines = append(lines, "", "Big-3 lift profiles (soft context; use only if the exercise is related):")
			if len(related) > 0 {
				lines = append(lines, "Most related competition lift(s): "+strings.Join(related, ", "))
			}
		}
	} else {
		target := map[string]string{"squat": "squat", "back squat": "squat", "bench": "bench", "bench press": "bench", "deadlift": "deadlift", "conventional deadlift": "deadlift", "sumo deadlift": "deadlift"}[strings.ToLower(strings.TrimSpace(name))]
		if target == "" && (category == "squat" || category == "bench" || category == "deadlift") {
			target = category
		}
		selected = nil
		for _, item := range profiles {
			if strings.EqualFold(fmt.Sprint(item["lift"]), target) && target != "" {
				selected = []map[string]any{item}
				break
			}
		}
	}
	for _, item := range selected {
		lift, _ := item["lift"].(string)
		lines = append(lines, "", "Lift profile ("+lift+"):")
		described := defs.Describe(item)
		technique, _ := described["technique"].(map[string]any)
		for _, field := range defs[lift] {
			if value, ok := technique[field.Label]; ok {
				lines = append(lines, fmt.Sprintf("  %s: %v", field.Label, value))
			}
		}
		lines = append(lines, fmt.Sprintf("  Volume tolerance: %v", described["volume_tolerance"]))
		if notes, ok := described["notes"].(string); ok && notes != "" {
			lines = append(lines, "  Notes: "+notes)
		}
	}
	return strings.Join(lines, "\n")
}

func ExerciseEstimate(defs profile.Definitions, programs Programs, muscle bool) func(context.Context, map[string]any, execution.Inferer) (any, error) {
	return func(ctx context.Context, args map[string]any, infer execution.Inferer) (any, error) {
		exercise, _ := args["exercise"].(map[string]any)
		athlete, _ := args["pk"].(string)
		program := programs.Context(ctx, athlete)
		selected, _ := args["lift_profiles"].([]any)
		if len(selected) == 0 {
			selected, _ = program["lift_profiles"].([]any)
		}
		profiles := []map[string]any{}
		for _, raw := range selected {
			if item, ok := raw.(map[string]any); ok {
				profiles = append(profiles, item)
			}
		}
		properties := map[string]any{}
		name, prompt := "estimate_fatigue_profile", fatiguePrompt
		if muscle {
			name, prompt = "estimate_muscle_groups", musclePrompt
			for _, key := range []string{"primary_muscles", "secondary_muscles", "tertiary_muscles"} {
				properties[key] = map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": allowedMuscles}}
			}
		} else {
			for key, description := range map[string]string{"axial": "Spinal compression loading 0.0-1.0", "neural": "CNS demand baseline 0.0-1.0", "peripheral": "Local muscle damage potential 0.0-1.0", "systemic": "Cardiovascular/metabolic demand 0.0-1.0"} {
				properties[key] = map[string]any{"type": "number", "description": description}
			}
		}
		properties["reasoning"] = map[string]any{"type": "string"}
		required := []string{}
		if muscle {
			required = []string{"primary_muscles", "secondary_muscles", "tertiary_muscles", "reasoning"}
		} else {
			required = []string{"axial", "neural", "peripheral", "systemic", "reasoning"}
		}
		description := "Estimate 4-dimensional fatigue profile for an exercise"
		if muscle {
			description = "Estimate primary, secondary, and tertiary muscle groups for an exercise"
		}
		tool := map[string]any{"type": "function", "function": map[string]any{"name": name, "description": description, "parameters": map[string]any{"type": "object", "properties": properties, "required": required}}}
		response, err := infer(ctx, cache.Request{Messages: []any{map[string]any{"role": "system", "content": strings.TrimSpace(prompt)}, map[string]any{"role": "user", "content": exerciseMessage(defs, exercise, program, profiles, muscle)}}, Tools: []any{tool}})
		if err != nil {
			return exerciseFallback(muscle, err.Error()), nil
		}
		answer, err := toolArguments(response)
		if err != nil {
			return exerciseFallback(muscle, err.Error()), nil
		}
		if len(answer) == 0 {
			return exerciseFallback(muscle, "no tool call"), nil
		}
		if muscle {
			buckets := [][]string{}
			for _, key := range required[:3] {
				values, _ := answer[key].([]any)
				bucket := []string{}
				for _, value := range values {
					if text, ok := value.(string); ok {
						bucket = append(bucket, text)
					}
				}
				buckets = append(buckets, bucket)
			}
			groups := profile.MuscleGroups(buckets...)
			return map[string]any{"primary_muscles": groups[0], "secondary_muscles": groups[1], "tertiary_muscles": groups[2], "reasoning": answer["reasoning"]}, nil
		}
		result := map[string]any{"reasoning": answer["reasoning"]}
		for _, key := range required[:4] {
			value, ok := answer[key].(float64)
			if !ok {
				value = 0.3
				if key == "peripheral" {
					value = 0.5
				}
			}
			result[key] = math.RoundToEven(math.RoundToEven(value/0.05)*0.05*100) / 100
		}
		return result, nil
	}
}

func exerciseFallback(muscle bool, reason string) map[string]any {
	if muscle {
		return map[string]any{"primary_muscles": []string{}, "secondary_muscles": []string{}, "tertiary_muscles": []string{}, "reasoning": "AI estimation failed: " + reason}
	}
	return map[string]any{"axial": 0.3, "neural": 0.3, "peripheral": 0.5, "systemic": 0.3, "reasoning": "AI estimation failed: " + reason}
}
