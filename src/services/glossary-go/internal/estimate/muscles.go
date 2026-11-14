package estimate

import (
	"context"
	"slices"
	"strings"

	"powerlifting/glossary-go/internal/execution"
	"powerlifting/glossary-go/internal/exercise"
)

type Muscles struct {
	Primary, Secondary, Tertiary []string
	Reasoning                    string
}

var aliases = map[string]string{
	"tibialis anterior": "tibialis_anterior", "hip flexors": "hip_flexors", "front delts": "front_delts",
	"front deltoids": "front_delts", "side delts": "side_delts", "lateral delts": "side_delts",
	"rear delts": "rear_delts", "rear deltoids": "rear_delts", "teres major": "teres_major",
	"lower back": "lower_back", "adductor": "adductors", "serratus anterior": "serratus",
}

var allowedMuscles = func() []string {
	properties := tool("estimate_muscle_groups")["function"].(map[string]any)["parameters"].(map[string]any)["properties"].(map[string]any)
	enum := properties["primary_muscles"].(map[string]any)["items"].(map[string]any)["enum"].([]any)
	allowed := make([]string, 0, len(enum))
	for _, muscle := range enum {
		allowed = append(allowed, muscle.(string))
	}
	return allowed
}()

func canonicalMuscle(raw string) string {
	token := strings.ReplaceAll(strings.ReplaceAll(strings.ToLower(strings.TrimSpace(raw)), "-", "_"), " ", "_")
	if alias, ok := aliases[strings.ReplaceAll(token, "_", " ")]; ok {
		token = alias
	}
	if slices.Contains(allowedMuscles, token) {
		return token
	}
	return ""
}

func bucket(values any, seen map[string]bool, limit int) []string {
	list, _ := values.([]any)
	out := []string{}
	for _, raw := range list {
		text, _ := raw.(string)
		muscle := canonicalMuscle(text)
		if muscle == "" || seen[muscle] {
			continue
		}
		seen[muscle] = true
		out = append(out, muscle)
		if len(out) >= limit {
			break
		}
	}
	return out
}

func EstimateMuscles(ctx context.Context, infer execution.Inferer, item exercise.Item, athlete *Athlete) (Muscles, error) {
	data := struct {
		Exercise                   exerciseView
		AthleteLines, ProfileLines []string
	}{Exercise: view(item, "Existing ")}
	if athlete != nil {
		name := strings.ToLower(strings.TrimSpace(exercise.Text(item, "name")))
		data.AthleteLines = athlete.metricLines()
		data.ProfileLines = athlete.relatedProfiles(name, strings.ToLower(exercise.Text(item, "category")))
	}
	args, err := ask(ctx, infer, render("muscle_group_system", nil), render("muscle_group_user", data), tool("estimate_muscle_groups"))
	if err != nil {
		return Muscles{}, err
	}
	seen := map[string]bool{}
	reasoning, _ := args["reasoning"].(string)
	return Muscles{
		Primary:   bucket(args["primary_muscles"], seen, 4),
		Secondary: bucket(args["secondary_muscles"], seen, 5),
		Tertiary:  bucket(args["tertiary_muscles"], seen, 5),
		Reasoning: reasoning,
	}, nil
}
