package serve

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"powerlifting/federation/internal/auth"
	"powerlifting/federation/internal/contract"
	"powerlifting/federation/internal/service"
	"strings"
	"testing"
)

type access struct{}

func (access) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) (map[string]any, error) {
	return map[string]any{"athlete_pk": c.Athlete}, nil
}

type memory struct {
	item    map[string]any
	updated string
}

func (m *memory) Get(context.Context, string) (map[string]any, error) { return m.item, nil }
func (m *memory) Put(_ context.Context, v map[string]any) error       { m.item = v; return nil }
func (m *memory) List(context.Context) ([]map[string]any, error) {
	return []map[string]any{{"pk": "FED#one", "name": "One"}}, nil
}
func (m *memory) Update(_ context.Context, id string, _ map[string]any) error {
	m.updated = id
	return nil
}

type versions struct{}

func (versions) Bump(context.Context, string) error { return nil }
func TestFederationOperations(t *testing.T) {
	reg, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	db := &memory{}
	handler := Handler(service.New(reg, access{}, db, versions{}, slog.New(slog.NewTextHandler(io.Discard, nil))), slog.New(slog.NewTextHandler(io.Discard, nil)))
	call := func(name, body string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(http.MethodPost, "/operations/"+name, strings.NewReader(body))
		r.Header.Set("Content-Type", "application/json")
		r.Header.Set("X-Athlete-Pk", "a")
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	out := call("federation_master_list", `{}`)
	var list []map[string]any
	if out.Code != 200 || json.Unmarshal(out.Body.Bytes(), &list) != nil || list[0]["pk"] != "FED#one" {
		t.Fatalf("list %d: %s", out.Code, out.Body.String())
	}
	out = call("federation_master_update", `{"master_id":"one","updates":{"name":"New"}}`)
	if out.Code != 200 || db.updated != "one" {
		t.Fatalf("update %d: %s", out.Code, out.Body.String())
	}
	out = call("federation_user_library_set", `{"federations":[{"id":"one"}],"qualification_standards":[]}`)
	if out.Code != 200 {
		t.Fatalf("save %d: %s", out.Code, out.Body.String())
	}
	out = call("federation_user_library_get", `{}`)
	if out.Code != 200 || !strings.Contains(out.Body.String(), `"id":"one"`) {
		t.Fatalf("get %d: %s", out.Code, out.Body.String())
	}
}
