package estimate

import (
	"errors"
	"strings"

	"powerlifting/glossary/internal/exercise"
)

var competitionLifts = []string{"squat", "bench", "deadlift"}

func parseLiftTransfer(raw any) (exercise.Item, error) {
	args, _ := raw.(map[string]any)
	transfer := exercise.Item{"source": "ai"}
	for _, lift := range competitionLifts {
		value, ok := args[lift].(float64)
		if !ok {
			return nil, errors.New("lift transfer lacks " + lift)
		}
		transfer[lift] = roundedStep(value)
	}
	reasoning, _ := args["reasoning"].(string)
	transfer["reasoning"] = strings.TrimSpace(reasoning)
	return transfer, nil
}
