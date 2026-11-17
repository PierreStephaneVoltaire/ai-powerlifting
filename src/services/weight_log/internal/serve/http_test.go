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

	"powerlifting/weight-log/internal/auth"
	"powerlifting/weight-log/internal/contract"
	"powerlifting/weight-log/internal/service"
	"powerlifting/weight-log/internal/store"
)

type access struct{}

func (access) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) (map[string]any, error) {
	return map[string]any{"athlete_pk": c.Athlete}, nil
}

type memory struct {
	data     map[string]map[string]any
	conflict bool
}

func (m *memory) Get(_ context.Context, pk, sk string) (map[string]any, error) {
	v := m.data[pk+"/"+sk]
	if v == nil {
		return nil, nil
	}
	b, _ := json.Marshal(v)
	var copy map[string]any
	json.Unmarshal(b, &copy)
	return copy, nil
}
func (m *memory) Put(_ context.Context, v map[string]any, _ string) error {
	if m.conflict {
		return store.ErrConflict
	}
	b, _ := json.Marshal(v)
	var copy map[string]any
	_ = json.Unmarshal(b, &copy)
	m.data[v["pk"].(string)+"/"+v["sk"].(string)] = copy
	return nil
}

type versions struct{}

func (versions) Bump(context.Context, string) error { return nil }
func TestWeightLogRoundTrip(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{data: map[string]map[string]any{
		"a/program#current":    {"ref_sk": "program#v001", "current_block_id": "new"},
		"a/program#v001":       {"meta": map[string]any{"current_block_id": "new", "blocks": []any{map[string]any{"id": "old", "start_date": "2025-01-01"}, map[string]any{"id": "new", "start_date": "2026-01-01"}}}},
		"a/weight_log#current": {"pk": "a", "sk": "weight_log#current", "updated_at": "v1", "entries": []any{map[string]any{"date": "2025-02-01", "kg": 90}, map[string]any{"date": "2026-02-01", "kg": 92}}},
	}}
	handler := Handler(service.New(registry, access{}, db, versions{}, slog.New(slog.NewTextHandler(io.Discard, nil))), slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(name, body string) (int, map[string]any) {
		t.Helper()
		req := httptest.NewRequest(http.MethodPost, "/operations/"+name, strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Athlete-Pk", "a")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		var v map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &v); err != nil {
			t.Fatal(err)
		}
		return w.Code, v
	}
	status, got := call("weight_log_get", `{}`)
	if status != 200 || len(got["entries"].([]any)) != 1 {
		t.Fatalf("get %d: %#v", status, got)
	}
	status, _ = call("weight_log_get", `{"pk":"other"}`)
	if status != 403 {
		t.Fatalf("expected cross-athlete request to be rejected, got %d", status)
	}
	status, got = call("weight_log_add", `{"date":"2026-02-01","weight_kg":95}`)
	if status != 200 || got["entries"].([]any)[0].(map[string]any)["kg"] != float64(95) {
		t.Fatalf("add %d: %#v", status, got)
	}
	if len(db.data["a/weight_log#current"]["entries"].([]any)) != 2 {
		t.Fatal("lost older block")
	}
	db.conflict = true
	status, _ = call("weight_log_remove", `{"date":"2026-02-01"}`)
	if status != 409 {
		t.Fatalf("expected conflict, got %d", status)
	}
}
