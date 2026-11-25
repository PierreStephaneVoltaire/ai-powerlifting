package service

import (
	"context"
	_ "embed"
	"encoding/json"
	"strings"
	"time"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
)

//go:embed stimulus_prompt.txt
var stimulusPrompt string

func Stimulus(definitions profile.Definitions, programs Programs) func(context.Context, map[string]any, execution.Inferer) (any, error) {
	return func(ctx context.Context, args map[string]any, infer execution.Inferer) (any, error) {
		input, _ := args["profile"].(map[string]any)
		clean := definitions.Clean(input)
		if clean == nil {
			return nil, apperr.Validation("Invalid lift. Expected squat, bench, or deadlift.")
		}
		if missing := definitions.Missing(clean); len(missing) != 0 {
			return nil, apperr.Validation("Choose every option before estimating: " + strings.Join(missing, ", "))
		}
		described := definitions.Describe(clean)
		athlete, _ := args["pk"].(string)
		if athlete != "" {
			program := programs.Context(ctx, athlete)
			meta, _ := program["meta"].(map[string]any)
			if details := profile.Athlete(meta); len(details) != 0 {
				described["athlete"] = details
			}
		}
		message, err := json.MarshalIndent(described, "", "  ")
		if err != nil {
			return nil, err
		}
		tool := map[string]any{"type": "function", "function": map[string]any{"name": "estimate_lift_profile_stimulus", "description": "Estimate a 1-2 INOL stimulus coefficient from a structured lift profile.", "parameters": map[string]any{"type": "object", "properties": map[string]any{"stimulus_coefficient": map[string]any{"type": "number", "minimum": 1, "maximum": 2, "description": "1.00 plus the summed per-field adjustments, two decimals"}, "confidence": map[string]any{"type": "string", "enum": []any{"low", "medium", "high"}}, "reasoning": map[string]any{"type": "string"}}, "required": []any{"stimulus_coefficient", "confidence", "reasoning"}}}}
		response, err := infer(ctx, cache.Request{Messages: []any{map[string]any{"role": "system", "content": strings.TrimSpace(stimulusPrompt)}, map[string]any{"role": "user", "content": "Estimate the stimulus coefficient for this lift profile:\n" + string(message)}}, Tools: []any{tool}})
		if err != nil {
			return nil, err
		}
		answer, err := toolArguments(response)
		if err != nil {
			return nil, err
		}
		if len(answer) == 0 {
			return nil, apperr.Validation("The estimate returned no result")
		}
		coefficient, ok := answer["stimulus_coefficient"].(float64)
		if !ok {
			coefficient = 1
		}
		confidence, _ := answer["confidence"].(string)
		confidence = strings.ToLower(confidence)
		if confidence != "low" && confidence != "medium" && confidence != "high" {
			confidence = "low"
		}
		reasoning, _ := answer["reasoning"].(string)
		return map[string]any{"lift": clean["lift"], "stimulus_coefficient": profile.Stimulus(coefficient), "stimulus_coefficient_confidence": confidence, "stimulus_coefficient_reasoning": strings.TrimSpace(reasoning), "stimulus_coefficient_updated_at": time.Now().UTC().Format(time.RFC3339Nano)}, nil
	}
}
