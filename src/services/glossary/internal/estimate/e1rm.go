package estimate

import (
	"context"
	"encoding/json"
	"errors"

	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/exercise"
)

type E1RM struct {
	Kg, Ratio                      float64
	PrimaryLift, Basis, Confidence string
}

func EstimateE1RM(ctx context.Context, infer execution.Inferer, item exercise.Item, maxes map[string]any, profiles []map[string]any, instances []map[string]any) (E1RM, error) {
	name := exercise.Text(item, "name")
	payload, err := json.MarshalIndent(map[string]any{
		"missing_exercises": []string{name},
		"current_maxes":     maxes,
		"lift_profiles":     profiles,
		"body_metrics":      map[string]any{},
		"past_instances":    map[string]any{name: instances},
	}, "", "  ")
	if err != nil {
		return E1RM{}, err
	}
	args, err := ask(ctx, infer, render("e1rm_backfill_system", nil), string(payload), tool("report_e1rm_estimates"))
	if err != nil {
		return E1RM{}, err
	}
	estimates, _ := args["estimates"].([]any)
	if len(estimates) == 0 {
		return E1RM{}, errors.New("model returned no estimate")
	}
	first, _ := estimates[0].(map[string]any)
	estimate := E1RM{Kg: number(first["e1rm_kg"]), Ratio: number(first["ratio"])}
	estimate.PrimaryLift, _ = first["primary_lift_used"].(string)
	estimate.Basis, _ = first["basis"].(string)
	estimate.Confidence, _ = first["confidence"].(string)
	if estimate.Kg <= 0 {
		return E1RM{}, errors.New("model returned no usable e1RM")
	}
	return estimate, nil
}
