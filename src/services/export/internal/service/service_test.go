package service

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"testing"

	"powerlifting/export/internal/apperr"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
)

type allowAccess struct{}

func (allowAccess) Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error) {
	return map[string]any{}, nil
}

func TestUnfinishedServiceFailsClosedAfterAuthorization(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc := New(registry, allowAccess{}, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	caller := auth.Caller{Person: "person", Athlete: "athlete"}
	for _, test := range []struct {
		name   string
		args   map[string]any
		status int
	}{
		{"export_program_history", map[string]any{}, http.StatusServiceUnavailable},
		{"get_analysis_markdown", map[string]any{}, http.StatusServiceUnavailable},
		{"analytics.markdown", map[string]any{}, http.StatusServiceUnavailable},
		{"export_program_history", map[string]any{"pk": "another-athlete"}, http.StatusForbidden},
		{"export_program_history", map[string]any{"_access": map[string]any{"is_self": true}}, http.StatusForbidden},
	} {
		_, err = svc.Call(context.Background(), test.name, test.args, caller)
		var status *apperr.Error
		if !errors.As(err, &status) || status.Status != test.status {
			t.Errorf("%s: got %v, want status %d", test.name, err, test.status)
		}
	}
}
