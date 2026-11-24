package service

import (
	"context"
	_ "embed"
	"encoding/json"
	"strings"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
)

//go:embed suggest_prompt.txt
var suggestPrompt string

func Suggest(definitions profile.Definitions) func(context.Context, map[string]any, execution.Inferer) (any, error) {
	return func(ctx context.Context, args map[string]any, infer execution.Inferer) (any, error) {
		lift, _ := args["lift"].(string)
		if lift != "squat" && lift != "bench" && lift != "deadlift" {
			return nil, apperr.Validation("Invalid lift. Expected squat, bench, or deadlift.")
		}
		current, _ := args["profile"].(map[string]any)
		options, _ := current["options"].(map[string]any)
		selected := definitions.Options(lift, options)
		fields := map[string]any{}
		for _, field := range definitions[lift] {
			choices := map[string]any{}
			for _, option := range field.Options {
				choices[option.Value] = option.Label
			}
			fields[field.Key] = map[string]any{"label": field.Label, "options": choices}
		}
		description, _ := args["description"].(string)
		message, err := json.MarshalIndent(map[string]any{"lift": lift, "fields": fields, "already_selected": selected, "description": strings.TrimSpace(description)}, "", "  ")
		if err != nil {
			return nil, err
		}
		response, err := infer(ctx, cache.Request{Messages: []any{map[string]any{"role": "system", "content": strings.TrimSpace(suggestPrompt)}, map[string]any{"role": "user", "content": string(message)}}, Tools: []any{definitions.SuggestSchema(lift)}})
		if err != nil {
			return nil, err
		}
		answer, err := toolArguments(response)
		if err != nil {
			return nil, err
		}
		return definitions.Suggest(lift, options, answer), nil
	}
}

func toolArguments(response map[string]any) (map[string]any, error) {
	choices, _ := response["choices"].([]any)
	if len(choices) == 0 {
		return map[string]any{}, nil
	}
	choice, _ := choices[0].(map[string]any)
	message, _ := choice["message"].(map[string]any)
	calls, _ := message["tool_calls"].([]any)
	if len(calls) == 0 {
		return map[string]any{}, nil
	}
	call, _ := calls[0].(map[string]any)
	function, _ := call["function"].(map[string]any)
	args, _ := function["arguments"].(string)
	if args == "" {
		args = "{}"
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(args), &result); err != nil {
		return nil, err
	}
	return result, nil
}
