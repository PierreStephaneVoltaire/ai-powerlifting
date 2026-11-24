package serve

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
	"powerlifting/export/internal/hydration"
	"powerlifting/export/internal/service"
)

type allowAccess struct{}

func (allowAccess) Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error) {
	return map[string]any{"is_self": true}, nil
}

type programSource struct{}

func (programSource) Load(context.Context, string, string, string, string, map[string]any) (*hydration.Loaded, error) {
	return &hydration.Loaded{Program: map[string]any{"meta": map[string]any{"program_name": "Test"}}}, nil
}

func TestOperationsHonorAthleteIdentity(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	svc := service.New(registry, allowAccess{}, nil, nil, log)
	svc.Programs = programSource{}
	handler := Handler(svc, log)
	for _, operation := range []string{"export_program_history", "get_analysis_markdown", "analytics.markdown"} {
		for _, test := range []struct {
			body   string
			status int
		}{{`{"pk":"athlete"}`, http.StatusOK}, {`{"pk":"other"}`, http.StatusForbidden}} {
			req := httptest.NewRequest(http.MethodPost, "/operations/"+operation, bytes.NewBufferString(test.body))
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("X-Person-Pk", "person")
			req.Header.Set("X-Athlete-Pk", "athlete")
			out := httptest.NewRecorder()
			handler.ServeHTTP(out, req)
			if out.Code != test.status {
				t.Errorf("%s %s: got %d, want %d: %s", operation, test.body, out.Code, test.status, out.Body.String())
				continue
			}
			var body map[string]any
			if err := json.Unmarshal(out.Body.Bytes(), &body); err != nil {
				t.Errorf("%s invalid JSON: %v", operation, err)
			}
		}
	}
}
