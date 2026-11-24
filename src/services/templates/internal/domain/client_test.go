package domain

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/templates/internal/auth"
)

func TestCallForwardsScopedIdentityAndNestedJob(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/operations/program_get" || r.Header.Get("X-Person-Pk") != "person" || r.Header.Get("X-Athlete-Pk") != "athlete" || r.Header.Get("X-If-Turn-Id") != "turn" || r.Header.Get("X-PL-Nested-Operation") != "true" {
			t.Errorf("unexpected request: %s %#v", r.URL.Path, r.Header)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()
	client := Client{URLTemplate: server.URL}
	result, err := client.Call(context.Background(), "program", "program_get", map[string]any{}, auth.Caller{Person: "person", Athlete: "athlete", TurnID: "turn"})
	if err != nil || result["ok"] != true {
		t.Fatalf("result %v, error %v", result, err)
	}
}
