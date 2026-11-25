package data

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/export/internal/auth"
)

func TestAnalyticsForwardsNestedIdentity(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/operations/weekly_analysis" || r.Header.Get("X-Person-Pk") != "person" || r.Header.Get("X-Athlete-Pk") != "athlete" || r.Header.Get("X-If-Turn-Id") != "turn" || r.Header.Get("X-PL-Nested-Operation") != "true" {
			t.Errorf("unexpected request: %s %#v", r.URL.Path, r.Header)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"overview":{"week":4}}`))
	}))
	defer server.Close()
	client := AnalyticsClient{URL: server.URL}
	result, err := client.Weekly(context.Background(), auth.Caller{Person: "person", Athlete: "athlete", TurnID: "turn"}, map[string]any{"weeks": 4})
	if err != nil || result["overview"] == nil {
		t.Fatalf("result=%#v err=%v", result, err)
	}
	if got := result["overview"].(map[string]any)["week"]; got != json.Number("4") {
		t.Fatalf("week precision lost: %#v", got)
	}
}
