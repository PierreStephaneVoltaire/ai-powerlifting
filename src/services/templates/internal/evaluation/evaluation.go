package evaluation

import (
	_ "embed"
	"encoding/json"
	"errors"
	"strings"

	"powerlifting/templates/internal/cache"
)

//go:embed system.txt
var systemPrompt string

//go:embed formula.txt
var formulaReference string

//go:embed options.json
var optionData []byte

type option struct {
	Value string `json:"value"`
	Label string `json:"label"`
}
type field struct {
	Key     string   `json:"key"`
	Label   string   `json:"label"`
	Options []option `json:"options"`
}

var definitions = func() map[string][]field {
	var d map[string][]field
	if err := json.Unmarshal(optionData, &d); err != nil {
		panic(err)
	}
	return d
}()

func describe(input map[string]any) map[string]any {
	lift, _ := input["lift"].(string)
	options, _ := input["options"].(map[string]any)
	labels := map[string]any{}
	for _, field := range definitions[lift] {
		for _, option := range field.Options {
			if options[field.Key] == option.Value {
				labels[field.Label] = option.Label
				break
			}
		}
	}
	tolerance, _ := input["volume_tolerance"].(string)
	if tolerance == "" {
		tolerance = "moderate"
	}
	out := map[string]any{"lift": lift, "technique": labels, "volume_tolerance": tolerance}
	if notes, ok := input["notes"].(string); ok && notes != "" {
		out["notes"] = notes
	}
	return out
}

func Request(template, program, metrics map[string]any, goals any, context string) (cache.Request, error) {
	sourceMeta, _ := template["meta"].(map[string]any)
	meta := map[string]any{}
	for _, key := range []string{"name", "program_context", "estimated_weeks", "days_per_week"} {
		if value, ok := sourceMeta[key]; ok {
			meta[key] = value
		}
	}
	meta["program_context"] = context
	sessions := []any{}
	if list, ok := template["sessions"].([]any); ok {
		for _, raw := range list {
			if session, ok := raw.(map[string]any); ok {
				next := map[string]any{}
				for key, value := range session {
					if key != "date" && key != "id" {
						next[key] = value
					}
				}
				sessions = append(sessions, next)
			}
		}
	}
	phases := template["phases"]
	if phases == nil {
		phases = []any{}
	}
	profiles := []any{}
	if values, ok := program["lift_profiles"].([]any); ok {
		for _, raw := range values {
			if item, ok := raw.(map[string]any); ok {
				profiles = append(profiles, describe(item))
			}
		}
	}
	maxes := program["current_maxes"]
	if maxes == nil {
		maxes = map[string]any{}
	}
	shown := context
	if shown == "" {
		shown = "Not provided."
	}
	user, err := json.MarshalIndent(map[string]any{"program_context": shown, "template": map[string]any{"meta": meta, "phases": phases, "sessions": sessions}, "metrics": metrics, "athlete_context": map[string]any{"current_maxes": maxes, "lift_profiles": profiles, "goals": goals}}, "", "  ")
	if err != nil {
		return cache.Request{}, err
	}
	schema := map[string]any{"type": "object", "properties": map[string]any{
		"stance": map[string]any{"type": "string", "enum": []any{"continue", "monitor", "adjust", "critical"}}, "summary": map[string]any{"type": "string"}, "strengths": map[string]any{"type": "array", "items": map[string]any{"type": "string"}}, "weaknesses": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
		"suggestions":    map[string]any{"type": "array", "items": map[string]any{"type": "object", "properties": map[string]any{"type": map[string]any{"type": "string"}, "week": map[string]any{"type": []any{"number", "null"}}, "phase": map[string]any{"type": []any{"string", "null"}}, "exercise": map[string]any{"type": []any{"string", "null"}}, "rationale": map[string]any{"type": "string"}}, "required": []any{"type", "rationale"}}},
		"data_citations": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
	}, "required": []any{"stance", "summary", "strengths", "weaknesses", "suggestions"}}
	return cache.Request{Messages: []any{map[string]any{"role": "system", "content": strings.TrimSpace(systemPrompt) + "\n\n" + formulaReference}, map[string]any{"role": "user", "content": string(user)}}, Tools: []any{map[string]any{"type": "function", "function": map[string]any{"name": "report_template_evaluation", "description": "Report the evaluation of a training template", "parameters": schema}}}}, nil
}

func Parse(response map[string]any) (map[string]any, error) {
	choices, _ := response["choices"].([]any)
	if len(choices) == 0 {
		return nil, errors.New("No choices in LLM response")
	}
	choice, _ := choices[0].(map[string]any)
	message, _ := choice["message"].(map[string]any)
	toolCalls, _ := message["tool_calls"].([]any)
	var raw string
	if len(toolCalls) > 0 {
		first, _ := toolCalls[0].(map[string]any)
		function, _ := first["function"].(map[string]any)
		raw, _ = function["arguments"].(string)
	} else {
		raw, _ = message["content"].(string)
		raw = strings.TrimSpace(raw)
		if !strings.HasPrefix(raw, "{") {
			return nil, errors.New("No tool calls in LLM response")
		}
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil, err
	}
	return result, nil
}
