package serve

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"powerlifting/calculations/internal/auth"
	"powerlifting/calculations/internal/contract"
	"powerlifting/calculations/internal/service"
)

type access struct{}

func (access) Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error) {
	return map[string]any{}, nil
}
func TestOperations(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc := service.New(registry, access{})
	svc.Now = func() time.Time { return time.Date(2026, 11, 17, 12, 0, 0, 0, time.UTC) }
	handler := Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	cases := []struct {
		name, body, key string
		want            any
	}{
		{"lb_to_kg", `{"lb":220.462}`, "kg", float64(100)},
		{"kg_to_lb", `{"kg":100}`, "lb", 220.5},
		{"pct_of_max", `{"max_kg":185,"pct":85}`, "rounded_2_5_kg", 157.5},
		{"ipf_weight_classes", `{"sex":"F"}`, "sex", "F"},
		{"estimate_1rm", `{"weight_kg":100,"reps":5,"rpe":8}`, "e1rm", 122.7},
		{"calculate_dots", `{"total_kg":0,"bodyweight_kg":80,"sex":"male"}`, "dots", float64(0)},
		{"days_until", `{"target_date":"2026-11-10"}`, "days_elapsed_since", float64(7)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/operations/"+tc.name, strings.NewReader(tc.body))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, req)
			if w.Code != 200 {
				t.Fatalf("status %d: %s", w.Code, w.Body.String())
			}
			var result map[string]any
			if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
				t.Fatal(err)
			}
			if result[tc.key] != tc.want {
				t.Fatalf("got %v, want %v", result[tc.key], tc.want)
			}
		})
	}
}

func TestMCPAndValidation(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	handler := Handler(service.New(registry, access{}), slog.New(slog.NewTextHandler(io.Discard, nil)))
	for _, tc := range []struct {
		path, body string
		status     int
		contains   string
	}{
		{"/mcp", `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"kg_to_lb","arguments":{"kg":100}}}`, 200, `"lb":220.5`},
		{"/operations/kg_to_lb", `{"kg":0}`, 422, `validation`},
		{"/operations/kg_to_lb", `{"kg":1,"_person_pk":"forged"}`, 403, `forbidden`},
	} {
		req := httptest.NewRequest(http.MethodPost, tc.path, strings.NewReader(tc.body))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != tc.status || !strings.Contains(w.Body.String(), tc.contains) {
			t.Errorf("%s: %d %s", tc.path, w.Code, w.Body.String())
		}
	}
}
