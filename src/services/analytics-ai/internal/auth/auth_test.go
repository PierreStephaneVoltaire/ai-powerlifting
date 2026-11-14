package auth

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/contract"
)

func TestCallerHeaders(t *testing.T) {
	header := http.Header{}
	for name, value := range map[string]string{
		"X-Person-Pk": "person_1", "X-Athlete-Pk": "athlete_1", "X-PL-Source-Principal": "cluster.local/ns/pl/sa/pl-analytics-ai",
		"X-IF-Job-Id": "job_1", "X-IF-Turn-Id": "turn_1", "X-PL-Nested-Operation": "true", "X-IF-Generation-Id": "gen_1", "X-IF-Generation-Attempt": "3",
	} {
		header.Set(name, value)
	}
	caller := FromHeaders(header)
	if caller.Person != "person_1" || caller.Athlete != "athlete_1" || !caller.Nested || caller.ActiveJob() != "turn_1" || *caller.Generation != (Generation{"gen_1", 3}) {
		t.Fatalf("got %+v", caller)
	}
	if FromHeaders(http.Header{}).ActiveJob() != "" || (Caller{JobID: "job_1"}).ActiveJob() != "job_1" {
		t.Fatal("job fallback")
	}
	if identity := Identity(header); identity.JobID != "" || identity.Nested {
		t.Fatal("identity must ignore execution headers")
	}
}

func TestBackendRecognition(t *testing.T) {
	for source, want := range map[string]bool{
		"spiffe://cluster.local/ns/pl/sa/powerlifting-app-backend": true,
		"cluster.local/ns/pl/sa/powerlifting-app-backend":          true,
		"cluster.local/ns/pl/sa/pl-analytics-ai":                   false,
		"cluster.local/ns/pl/sa/x-powerlifting-app-backend2":       false,
		"": false,
	} {
		if got := (Caller{Source: source}).IsBackend(); got != want {
			t.Errorf("%q: %v", source, got)
		}
	}
	if ServiceAccount("spiffe://cluster.local/ns/pl/sa/pl-analytics") != "pl-analytics" || ServiceAccount("nothing") != "" {
		t.Fatal("service account parsing")
	}
}

func TestProfileAccessContext(t *testing.T) {
	var gotHeader http.Header
	var gotBody map[string]any
	status := http.StatusOK
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHeader = r.Header.Clone()
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &gotBody)
		if r.URL.Path != "/operations/access_context" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(`{"settings_pk":"settings_1","permissions":["analytics:read"]}`))
	}))
	defer server.Close()
	client := ProfileClient{URL: server.URL, HTTP: server.Client()}
	caller := Caller{Person: "person_1", Athlete: "athlete_1"}
	access, err := client.Fetch(context.Background(), "analytics.correlation", map[string]any{"blockKey": "b"}, caller)
	if err != nil || access.String("settings_pk") != "settings_1" {
		t.Fatalf("got %v %v", access, err)
	}
	if gotHeader.Get("X-Person-Pk") != "person_1" || gotHeader.Get("X-Athlete-Pk") != "athlete_1" || gotBody["operation"] != "analytics.correlation" {
		t.Fatalf("unexpected request %v %v", gotHeader, gotBody)
	}
	status = http.StatusForbidden
	if _, err := client.Fetch(context.Background(), "x", nil, caller); err.(*apperr.Error).Status != http.StatusForbidden {
		t.Fatalf("got %v", err)
	}
	server.Close()
	if _, err := client.Fetch(context.Background(), "x", nil, caller); err.(*apperr.Error).Status != http.StatusServiceUnavailable {
		t.Fatalf("an unreachable permission service is unavailable, got %v", err)
	}
}

func TestScope(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	operation, _ := registry.Get("block_correlation_analysis")
	caller := Caller{Person: "person_1", Athlete: "athlete_1"}
	scoped, err := Scope(operation, map[string]any{"pk": "athlete_1", "block_key": "b"}, caller, Access{})
	if err != nil || scoped["pk"] != "athlete_1" {
		t.Fatalf("got %v %v", scoped, err)
	}
	scoped, err = Scope(operation, map[string]any{"block_key": "b"}, caller, Access{})
	if err != nil || scoped["pk"] != "athlete_1" {
		t.Fatalf("pk must be injected: %v %v", scoped, err)
	}
	if _, err := Scope(operation, map[string]any{"pk": "other"}, caller, Access{}); err == nil {
		t.Fatal("conflicting pk must be rejected")
	}
	if _, err := Scope(operation, map[string]any{"pk": ""}, caller, Access{}); err != nil {
		t.Fatalf("falsy selectors are ignored: %v", err)
	}
	if _, err := Scope(operation, map[string]any{}, Caller{Person: "p"}, Access{}); err == nil {
		t.Fatal("athlete scope is required")
	}
}
