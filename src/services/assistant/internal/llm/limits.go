package llm

import (
	"encoding/json"
	"fmt"
	"strings"
)

type LimitError struct{ Message string }

func (e *LimitError) Error() string { return e.Message }

func responseError(status int, raw []byte) error {
	message := fmt.Sprintf("litellm chat returned %d: %.300s", status, raw)
	var payload struct {
		Error struct {
			Code    string `json:"code"`
			Type    string `json:"type"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if json.Unmarshal(raw, &payload) == nil {
		code := strings.ToLower(payload.Error.Code + " " + payload.Error.Type)
		detail := strings.ToLower(payload.Error.Message)
		if strings.Contains(code, "context_length_exceeded") || strings.Contains(code, "contextwindowexceeded") || strings.Contains(code, "max_tokens_exceeded") || strings.Contains(detail, "maximum context length") || strings.Contains(detail, "context window exceeded") {
			return &LimitError{Message: message}
		}
	}
	return fmt.Errorf("%s", message)
}
