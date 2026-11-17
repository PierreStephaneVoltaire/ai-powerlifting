package activities

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/assistant/internal/llm"
)

func TestModelCallDetectsLimitsAndDiscardsPartialTools(t *testing.T) {
	for _, tt := range []struct {
		name, body       string
		status           int
		limited, failure bool
	}{
		{"output", `{"choices":[{"finish_reason":"length","message":{"content":"partial","tool_calls":[{"id":"unsafe"}]}}]}`, 200, true, false},
		{"context", `{"error":{"code":"context_length_exceeded","message":"too long"}}`, 400, true, false},
		{"quota", `{"error":{"code":"insufficient_quota","message":"limit reached"}}`, 429, false, true},
		{"auth", `{"error":{"code":"invalid_api_key"}}`, 401, false, true},
		{"complete", `{"choices":[{"finish_reason":"stop","message":{"content":"complete"}}]}`, 200, false, false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(tt.status); fmt.Fprint(w, tt.body) }))
			defer server.Close()
			deps := Deps{LLM: llm.New(server.URL, "test"), Slots: make(chan struct{}, 1)}
			result, err := deps.ModelCall(context.Background(), ModelCallInput{Model: "fast"})
			if (result.Limit != "") != tt.limited || (err != nil) != tt.failure {
				t.Fatalf("result=%+v error=%v", result, err)
			}
			if tt.limited && (result.Content != "" || len(result.ToolCalls) != 0) {
				t.Fatal("partial output leaked")
			}
		})
	}
}
