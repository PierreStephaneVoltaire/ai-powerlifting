package workflow

import (
	"errors"
	"reflect"
	"testing"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
)

func TestModelLimitRetry(t *testing.T) {
	for _, tt := range []struct {
		name, model, stronger string
		outputs               []activities.ModelCallOutput
		failure               error
		models                []string
		wantError             bool
	}{
		{name: "complete", model: "fast", stronger: "strong", outputs: []activities.ModelCallOutput{{ChatResponse: llm.ChatResponse{Content: "complete"}}}, models: []string{"fast"}},
		{name: "limit then complete", model: "fast", stronger: "strong", outputs: []activities.ModelCallOutput{{Limit: "context"}, {ChatResponse: llm.ChatResponse{Content: "complete"}}}, models: []string{"fast", "strong"}},
		{name: "second limit stops", model: "fast", stronger: "strong", outputs: []activities.ModelCallOutput{{Limit: "context"}, {Limit: "output"}}, models: []string{"fast", "strong"}, wantError: true},
		{name: "already strongest", model: "strong", stronger: "strong", outputs: []activities.ModelCallOutput{{Limit: "output"}}, models: []string{"strong"}, wantError: true},
		{name: "no stronger configured", model: "fast", outputs: []activities.ModelCallOutput{{Limit: "output"}}, models: []string{"fast"}, wantError: true},
		{name: "unrelated error", model: "fast", stronger: "strong", failure: errors.New("unauthorized"), models: []string{"fast"}, wantError: true},
	} {
		t.Run(tt.name, func(t *testing.T) {
			var models []string
			result, err := modelWithLimitRetry(tt.model, tt.stronger, func(model string, retry bool) (activities.ModelCallOutput, error) {
				if retry != (len(models) == 1) {
					t.Fatal("incorrect retry policy")
				}
				models = append(models, model)
				if tt.failure != nil {
					return activities.ModelCallOutput{}, tt.failure
				}
				if len(models) > len(tt.outputs) {
					t.Fatal("unexpected extra model call")
				}
				return tt.outputs[len(models)-1], nil
			})
			if !reflect.DeepEqual(models, tt.models) || (err != nil) != tt.wantError {
				t.Fatalf("models=%v error=%v", models, err)
			}
			if err == nil && result.Content != "complete" {
				t.Fatalf("incomplete result: %+v", result)
			}
		})
	}
}
