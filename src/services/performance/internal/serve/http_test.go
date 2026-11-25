package serve

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"powerlifting/performance/internal/auth"
	"powerlifting/performance/internal/contract"
	"powerlifting/performance/internal/service"
	"strings"
	"testing"
)

type access struct{}

func (access) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) (map[string]any, error) {
	return map[string]any{"athlete_pk": c.Athlete, "competition_scope": map[string]any{"read": []any{"COMP#allowed"}}}, nil
}

type memory struct {
	data  map[string]map[string]any
	meets []map[string]any
}

func (m *memory) Get(_ context.Context, pk, sk string) (map[string]any, error) {
	v := m.data[pk+"/"+sk]
	if v == nil {
		return nil, nil
	}
	b, _ := json.Marshal(v)
	var result map[string]any
	_ = json.Unmarshal(b, &result)
	return result, nil
}
func (m *memory) Put(_ context.Context, v map[string]any) error {
	b, _ := json.Marshal(v)
	var result map[string]any
	_ = json.Unmarshal(b, &result)
	m.data[v["pk"].(string)+"/"+v["sk"].(string)] = result
	return nil
}
func (m *memory) Competitions(context.Context, string) ([]map[string]any, error) { return m.meets, nil }

type versions struct{}

func (versions) Bump(context.Context, string) error { return nil }
func TestPerformanceOperations(t *testing.T) {
	reg, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{data: map[string]map[string]any{"a/program#current": {"ref_sk": "program#v001"}, "a/program#v001": {"pk": "a", "sk": "program#v001", "current_maxes": map[string]any{"squat": 180}, "meta": map[string]any{}}}, meets: []map[string]any{{"master_id": "allowed", "user_status": "completed", "start_date": "2026-01-01", "results": map[string]any{"squat_kg": 190}}, {"master_id": "hidden", "user_status": "completed", "start_date": "2026-02-01", "results": map[string]any{"squat_kg": 200}}}}
	handler := Handler(service.New(reg, access{}, db, versions{}, slog.New(slog.NewTextHandler(io.Discard, nil))), slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(name, body string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(http.MethodPost, "/operations/"+name, strings.NewReader(body))
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Athlete-Pk", "a")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	out := call("health_update_current_maxes", `{"bench_kg":120}`)
	if out.Code != 200 || !strings.Contains(out.Body.String(), `"squat":180`) {
		t.Fatalf("maxes %d: %s", out.Code, out.Body.String())
	}
	out = call("max_target_update", `{"squat_kg":190,"bench_kg":125,"deadlift_kg":230}`)
	if out.Code != 200 || !strings.Contains(out.Body.String(), `"total_kg":545`) {
		t.Fatalf("target %d: %s", out.Code, out.Body.String())
	}
	out = call("max_history_add", `{"entry":{"date":"2026-03-01","squat_kg":180,"bench_kg":120,"_access":"forged"}}`)
	if out.Code != 200 || strings.Contains(out.Body.String(), "_access") || !strings.Contains(out.Body.String(), `"total_kg":300`) {
		t.Fatalf("add %d: %s", out.Code, out.Body.String())
	}
	out = call("max_history_get", `{}`)
	if out.Code != 200 || !strings.Contains(out.Body.String(), "competition#allowed") || strings.Contains(out.Body.String(), "competition#hidden") {
		t.Fatalf("history %d: %s", out.Code, out.Body.String())
	}
	out = call("max_history_get", `{"start_date":"2026-04-01","end_date":"2026-01-01"}`)
	if out.Code != 422 {
		t.Fatalf("invalid dates %d: %s", out.Code, out.Body.String())
	}
}
