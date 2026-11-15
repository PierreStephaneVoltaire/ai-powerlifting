package estimate

import (
	"errors"
	"strings"

	"powerlifting/glossary/internal/exercise"
)

type Fatigue struct {
	Profile   exercise.Item
	Reasoning string
}

func parseFatigue(raw any) (Fatigue, error) {
	args, _ := raw.(map[string]any)
	profile := exercise.Item{}
	for _, axis := range []string{"axial", "neural", "peripheral", "systemic"} {
		value, ok := args[axis].(float64)
		if !ok {
			return Fatigue{}, errors.New("fatigue lacks " + axis)
		}
		profile[axis] = roundedStep(value)
	}
	reasoning, _ := args["reasoning"].(string)
	return Fatigue{Profile: profile, Reasoning: strings.TrimSpace(reasoning)}, nil
}
