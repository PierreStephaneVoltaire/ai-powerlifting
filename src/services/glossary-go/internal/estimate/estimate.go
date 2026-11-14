package estimate

import (
	"bytes"
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strings"
	"text/template"

	"powerlifting/glossary-go/internal/cache"
	"powerlifting/glossary-go/internal/execution"
	"powerlifting/glossary-go/internal/exercise"
)

//go:embed templates/*.tmpl
var templateFiles embed.FS

//go:embed tools/*.json
var toolFiles embed.FS

var templates = template.Must(template.New("").Funcs(template.FuncMap{
	"join": func(values []string) string { return strings.Join(values, ", ") },
}).ParseFS(templateFiles, "templates/*.tmpl"))

func render(name string, data any) string {
	var out bytes.Buffer
	if err := templates.ExecuteTemplate(&out, name+".tmpl", data); err != nil {
		panic(err)
	}
	return strings.TrimSpace(out.String())
}

func tool(name string) map[string]any {
	raw, err := toolFiles.ReadFile("tools/" + name + ".json")
	if err != nil {
		panic(err)
	}
	var definition map[string]any
	if err := json.Unmarshal(raw, &definition); err != nil {
		panic(err)
	}
	return definition
}

func ask(ctx context.Context, infer execution.Inferer, system, user string, definition map[string]any) (map[string]any, error) {
	response, err := infer(ctx, cache.Request{
		Messages: []any{map[string]any{"role": "system", "content": system}, map[string]any{"role": "user", "content": user}},
		Tools:    []any{definition},
	})
	if err != nil {
		return nil, err
	}
	choices, _ := response["choices"].([]any)
	if len(choices) == 0 {
		return nil, errors.New("no choices in model response")
	}
	choice, _ := choices[0].(map[string]any)
	message, _ := choice["message"].(map[string]any)
	calls, _ := message["tool_calls"].([]any)
	if len(calls) == 0 {
		return nil, errors.New("no tool call in model response")
	}
	call, _ := calls[0].(map[string]any)
	function, _ := call["function"].(map[string]any)
	arguments, _ := function["arguments"].(string)
	var parsed map[string]any
	if err := json.Unmarshal([]byte(arguments), &parsed); err != nil {
		return nil, fmt.Errorf("tool arguments: %w", err)
	}
	return parsed, nil
}

type exerciseView struct {
	Name, Category, Equipment, Description, HowToPerform, WhyDoIt, MusclePrefix string
	Primary, Secondary, Tertiary                                                []string
}

func (v exerciseView) Label(name string) string {
	if v.MusclePrefix == "" {
		return name
	}
	return v.MusclePrefix + strings.ToLower(name)
}

func view(item exercise.Item, musclePrefix string) exerciseView {
	name := exercise.Text(item, "name")
	if name == "" {
		name = "Unknown"
	}
	return exerciseView{
		Name: name, Category: exercise.Text(item, "category"), Equipment: exercise.Text(item, "equipment"),
		Description: exercise.Text(item, "description"), HowToPerform: exercise.Text(item, "how_to_perform"), WhyDoIt: exercise.Text(item, "why_do_it"),
		MusclePrefix: musclePrefix,
		Primary:      exercise.Strings(item, "primary_muscles"), Secondary: exercise.Strings(item, "secondary_muscles"), Tertiary: exercise.Strings(item, "tertiary_muscles"),
	}
}

func number(value any) float64 {
	parsed, _ := value.(float64)
	return parsed
}

func roundedStep(value float64) float64 {
	return math.Round(math.Max(0, math.Min(1, math.Round(value/0.05)*0.05))*100) / 100
}
