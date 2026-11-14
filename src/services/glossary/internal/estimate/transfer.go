package estimate

import (
	"context"
	"strings"

	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
)

func EstimateLiftTransfer(ctx context.Context, infer execution.Inferer, item exercise.Item) (exercise.Item, error) {
	args, err := ask(ctx, infer, render("lift_transfer_system", nil), render("lift_transfer_user", struct{ Exercise exerciseView }{view(item, "")}), tool("estimate_lift_transfer"))
	if err != nil {
		return nil, err
	}
	reasoning, _ := args["reasoning"].(string)
	return exercise.Item{
		"squat":     roundedStep(number(args["squat"])),
		"bench":     roundedStep(number(args["bench"])),
		"deadlift":  roundedStep(number(args["deadlift"])),
		"source":    "ai",
		"reasoning": strings.TrimSpace(reasoning),
	}, nil
}
