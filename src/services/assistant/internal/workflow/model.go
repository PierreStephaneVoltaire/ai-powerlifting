package workflow

import (
	"fmt"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
)

func modelWithLimitRetry(model, stronger string, invoke func(string, bool) (activities.ModelCallOutput, error)) (llm.ChatResponse, error) {
	output, err := invoke(model, false)
	if err != nil {
		return llm.ChatResponse{}, err
	}
	if output.Limit == "" {
		return output.ChatResponse, nil
	}
	if stronger == "" || stronger == model {
		return llm.ChatResponse{}, fmt.Errorf("%s No stronger model is configured", output.Limit)
	}
	output, err = invoke(stronger, true)
	if err != nil {
		return llm.ChatResponse{}, fmt.Errorf("stronger-model retry failed: %w", err)
	}
	if output.Limit != "" {
		return llm.ChatResponse{}, fmt.Errorf("stronger-model retry reached a limit: %s", output.Limit)
	}
	return output.ChatResponse, nil
}
