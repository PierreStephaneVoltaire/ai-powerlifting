package serve

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"powerlifting/goals/internal/auth"
	"powerlifting/goals/internal/contract"
	"powerlifting/goals/internal/service"
	"strings"
	"testing"
)

type access struct{}

func (access) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) (map[string]any, error) {
	return map[string]any{"athlete_pk": c.Athlete}, nil
}

type memory struct{ data map[string]map[string]any }

func (m *memory) List(_ context.Context, _ string) ([]map[string]any, error) {
	out := []map[string]any{}
	for _, v := range m.data {
		out = append(out, v)
	}
	return out, nil
}
func (m *memory) Put(_ context.Context, item map[string]any) error {
	m.data[item["id"].(string)] = item
	return nil
}
func (m *memory) Delete(_ context.Context, _, id string) error { delete(m.data, id); return nil }

type versions struct{}

func (versions) Bump(context.Context, string) error { return nil }
func TestGoalReplacement(t *testing.T) {
	reg, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{data: map[string]map[string]any{"old": {"id": "old", "title": "Old", "target_competition_ids": []any{"meet"}}, "remove": {"id": "remove", "title": "Remove"}}}
	handler := Handler(service.New(reg, access{}, db, versions{}, slog.New(slog.NewTextHandler(io.Discard, nil))), slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(name, body string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodPost, "/operations/"+name, strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Athlete-Pk", "athlete")
		out := httptest.NewRecorder()
		handler.ServeHTTP(out, req)
		return out
	}
	out := call("goals_replace", `{"goals":[{"id":"old","title":"Target","priority":"primary"},{"title":"New"}]}`)
	if out.Code != 200 {
		t.Fatalf("replace %d: %s", out.Code, out.Body.String())
	}
	if len(db.data) != 2 || db.data["old"]["target_competition_ids"].([]any)[0] != "meet" {
		t.Fatalf("bad stored goals: %#v", db.data)
	}
	out = call("goals_list", `{}`)
	var list []map[string]any
	if out.Code != 200 || json.Unmarshal(out.Body.Bytes(), &list) != nil || len(list) != 2 {
		t.Fatalf("list %d: %s", out.Code, out.Body.String())
	}
	out = call("goals_replace", `{"goals":[]}`)
	if out.Code != 200 || len(db.data) != 0 {
		t.Fatalf("clear %d: %s", out.Code, out.Body.String())
	}
}
