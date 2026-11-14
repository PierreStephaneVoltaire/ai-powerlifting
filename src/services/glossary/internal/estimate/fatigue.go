package estimate

import (
	"context"
	"strings"

	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
)

type Fatigue struct {
	Profile   exercise.Item
	Reasoning string
}

func EstimateFatigue(ctx context.Context, infer execution.Inferer, item exercise.Item, athlete *Athlete) (Fatigue, error) {
	data := struct {
		Exercise                   exerciseView
		AthleteLines, ProfileLines []string
	}{Exercise: view(item, "")}
	if athlete != nil {
		name := strings.ToLower(strings.TrimSpace(exercise.Text(item, "name")))
		data.AthleteLines = athlete.metricLines()
		data.ProfileLines = athlete.matchedProfile(name, strings.ToLower(exercise.Text(item, "category")))
	}
	args, err := ask(ctx, infer, render("fatigue_system", nil), render("fatigue_user", data), tool("estimate_fatigue_profile"))
	if err != nil {
		return Fatigue{}, err
	}
	reasoning, _ := args["reasoning"].(string)
	profile := exercise.Item{}
	for _, axis := range []string{"axial", "neural", "peripheral", "systemic"} {
		profile[axis] = roundedStep(number(args[axis]))
	}
	return Fatigue{Profile: profile, Reasoning: strings.TrimSpace(reasoning)}, nil
}
