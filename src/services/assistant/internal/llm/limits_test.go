package llm

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestStreamingLimitSignals(t *testing.T) {
	for _, tt := range []struct {
		name, body string
		status     int
		limitError bool
	}{
		{"http context", `{"error":{"code":"context_length_exceeded"}}`, 400, true},
		{"stream context", "data: {\"error\":{\"code\":\"context_length_exceeded\"}}\n\n", 200, true},
		{"output", "data: {\"choices\":[{\"delta\":{\"content\":\"partial\"},\"finish_reason\":\"length\"}]}\n\ndata: [DONE]\n\n", 200, false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(tt.status); fmt.Fprint(w, tt.body) }))
			defer server.Close()
			result, err := New(server.URL, "test").ChatStream(context.Background(), ChatRequest{Model: "fast"}, nil)
			var limit *LimitError
			if errors.As(err, &limit) != tt.limitError {
				t.Fatalf("error=%v", err)
			}
			if !tt.limitError && (err != nil || result.FinishReason != "length") {
				t.Fatalf("result=%+v error=%v", result, err)
			}
		})
	}
}
