package reports

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"time"

	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/data"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/pyjson"
)

const minimumWeeks = 4

type SavedReport func(ctx context.Context, operation, blockKey string) map[string]any

type Env struct {
	Principal data.Principal
	Source    data.Source
	Infer     execution.Inferer
	Saved     SavedReport
	Now       func() time.Time
	Args      map[string]any
}

func (e Env) timestamp() string {
	return e.Now().UTC().Format("2006-01-02T15:04:05.000000Z")
}

func (e Env) text(key string) string {
	value, _ := e.Args[key].(string)
	return value
}

func (e Env) blockKey() string {
	if key := e.text("block_key"); key != "" {
		return key
	}
	return "current"
}

func ask(ctx context.Context, infer execution.Inferer, system, user string, tool map[string]any) (map[string]any, error) {
	request := cache.Request{
		Messages: []any{map[string]any{"role": "system", "content": system}, map[string]any{"role": "user", "content": user}},
		Tools:    []any{tool},
	}
	response, err := infer(ctx, request)
	if err != nil {
		return nil, err
	}
	choices, _ := response["choices"].([]any)
	if len(choices) == 0 {
		return nil, errors.New("No choices in LLM response")
	}
	choice, _ := choices[0].(map[string]any)
	message, _ := choice["message"].(map[string]any)
	calls, _ := message["tool_calls"].([]any)
	if len(calls) == 0 {
		return nil, errors.New("No tool calls in LLM response")
	}
	call, _ := calls[0].(map[string]any)
	function, _ := call["function"].(map[string]any)
	arguments, _ := function["arguments"].(string)
	parsed, err := pyjson.Decode([]byte(arguments))
	if err != nil {
		return nil, fmt.Errorf("tool arguments: %w", err)
	}
	object, ok := parsed.(map[string]any)
	if !ok {
		return nil, errors.New("tool arguments are not an object")
	}
	return object, nil
}

func pick(source map[string]any, key string, fallback any) any {
	if value, present := source[key]; present {
		return value
	}
	return fallback
}

func asString(value any) string {
	text, _ := value.(string)
	return text
}

func asMap(value any) map[string]any {
	object, _ := value.(map[string]any)
	return object
}

func asList(value any) []any {
	list, _ := value.([]any)
	return list
}

func asFloat(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case json.Number:
		parsed, err := typed.Float64()
		return parsed, err == nil
	case int:
		return float64(typed), true
	}
	return 0, false
}

func asInt(value any) int {
	number, _ := asFloat(value)
	return int(number)
}

type BlockEntry struct {
	Key       string
	Label     string
	Current   bool
	Start     string
	End       string
	WeekCount int
	Raw       map[string]any
}

func FindBlock(blocks []map[string]any, key string) (BlockEntry, bool) {
	for _, raw := range blocks {
		if asString(raw["blockKey"]) != key {
			continue
		}
		current, _ := raw["isCurrent"].(bool)
		return BlockEntry{
			Key: key, Label: asString(raw["label"]), Current: current, Start: asString(raw["startDate"]),
			End: asString(raw["endDate"]), WeekCount: asInt(raw["weekCount"]), Raw: raw,
		}, true
	}
	return BlockEntry{}, false
}

func Completed(session map[string]any) bool {
	if done, _ := session["completed"].(bool); done {
		return true
	}
	status := asString(session["status"])
	return status == "logged" || status == "completed"
}

func completedWeeks(sessions []map[string]any) []int {
	var weeks []int
	for _, session := range sessions {
		week := asInt(session["week_number"])
		if Completed(session) && week > 0 && !slices.Contains(weeks, week) {
			weeks = append(weeks, week)
		}
	}
	slices.Sort(weeks)
	return weeks
}

func InsufficientCorrelation(windowStart string, weeks, found int) map[string]any {
	return map[string]any{
		"findings": []any{}, "summary": "Insufficient data for correlation analysis.", "insufficient_data": true,
		"insufficient_data_reason": fmt.Sprintf("Only %d weeks of data found. Need at least %d.", found, minimumWeeks),
		"cached":                   false, "generated_at": "", "window_start": windowStart, "weeks": max(1, weeks),
	}
}

func InsufficientEvaluation(windowStart string, weeks int) map[string]any {
	report := emptyEvaluation("monitor", insufficientEvaluation)
	report["insufficient_data"] = true
	report["insufficient_data_reason"] = insufficientEvaluation
	report["cached"], report["generated_at"], report["window_start"], report["weeks"] = false, "", windowStart, max(1, weeks)
	return report
}

func Sufficient(weekCount int) bool { return weekCount >= minimumWeeks }
