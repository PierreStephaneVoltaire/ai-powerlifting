package serve

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/testenv"
	"powerlifting/profile/internal/value"
)

const backend = "spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend"

type fixture struct {
	handler http.Handler
	env     *testenv.Env
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	env := testenv.New(t)
	env.Seed("if-user",
		value.Item{"pk": "person_a", "mapped_pk": "person_a", "username": "person_a", "nickname": "alpha", "roles": []any{"athlete"}, "profile_complete": true},
	)
	return &fixture{env: env, handler: Handler(env.Service, slog.New(slog.NewTextHandler(io.Discard, nil)))}
}

func (f *fixture) do(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for name, v := range headers {
		request.Header.Set(name, v)
	}
	recorder := httptest.NewRecorder()
	f.handler.ServeHTTP(recorder, request)
	return recorder
}

var self = map[string]string{"X-Person-Pk": "person_a", "X-Athlete-Pk": "person_a"}

func TestEveryOperationIsDocumented(t *testing.T) {
	f := newFixture(t)
	response := f.do("GET", "/openapi.json", "", nil)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d", response.Code)
	}
	var document struct {
		Paths map[string]map[string]struct {
			OperationID string `json:"operationId"`
			Description string `json:"description"`
		} `json:"paths"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &document); err != nil {
		t.Fatal(err)
	}
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(registry.All()) != 42 {
		t.Fatalf("expected the 42 operations of profile.json, got %d", len(registry.All()))
	}
	for _, operation := range registry.All() {
		entry, ok := document.Paths["/operations/"+operation.Name]["post"]
		if !ok || entry.OperationID != operation.Name || entry.Description != operation.Description {
			t.Errorf("operation %s is not documented: %+v", operation.Name, entry)
		}
	}
	for _, path := range []string{"/mcp", "/health", "/healthz"} {
		if _, ok := document.Paths[path]; !ok {
			t.Errorf("%s is not documented", path)
		}
	}
	if docs := f.do("GET", "/docs", "", nil); docs.Code != http.StatusOK || !strings.Contains(docs.Body.String(), "swagger") {
		t.Fatalf("docs: %d", docs.Code)
	}
}

func TestHealthRoutes(t *testing.T) {
	f := newFixture(t)
	for _, path := range []string{"/health", "/healthz"} {
		response := f.do("GET", path, "", nil)
		if response.Code != http.StatusOK || strings.TrimSpace(response.Body.String()) != `{"status":"ok","domain":"profile"}` {
			t.Fatalf("%s: %d %s", path, response.Code, response.Body)
		}
	}
}

func TestAccessContextRoute(t *testing.T) {
	f := newFixture(t)
	response := f.do("POST", "/operations/access_context", `{}`, self)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d %s", response.Code, response.Body)
	}
	var context map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &context); err != nil {
		t.Fatal(err)
	}
	if context["person_pk"] != "person_a" || context["athlete_pk"] != "person_a" || context["is_self"] != true {
		t.Fatalf("context %v", context)
	}
	scope, _ := context["competition_scope"].(map[string]any)
	if scope["read"] != nil || scope["write"] != nil {
		t.Fatalf("self scope should be unrestricted: %v", scope)
	}
}

func TestSignedOutVisitorsReceiveABaseContextWithoutScans(t *testing.T) {
	f := newFixture(t)
	for _, person := range []string{"", "anonymous"} {
		response := f.do("POST", "/operations/access_context", `{}`, map[string]string{"X-Person-Pk": person, "X-Athlete-Pk": "person_a"})
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"is_self":false`) {
			t.Fatalf("%q: %d %s", person, response.Code, response.Body)
		}
	}
	if scans := f.env.DB.Count("Scan"); scans != 0 {
		t.Fatalf("signed-out access must not scan, saw %d", scans)
	}
}

func TestOwnerResolutionUsesPointReadsForPersonAndMappedAthlete(t *testing.T) {
	f := newFixture(t)
	f.env.Seed("if-user", value.Item{"pk": "person_b", "mapped_pk": "athlete_b", "roles": []any{"athlete"}})
	response := f.do("POST", "/operations/access_context", `{}`, map[string]string{"X-Person-Pk": "person_b", "X-Athlete-Pk": "athlete_b"})
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"is_self":true`) {
		t.Fatalf("%d %s", response.Code, response.Body)
	}
	if scans := f.env.DB.Count("Scan"); scans != 0 {
		t.Fatalf("an actor viewing its own mapped athlete must not scan, saw %d", scans)
	}
}

func TestUnknownOperationIs404(t *testing.T) {
	f := newFixture(t)
	response := f.do("POST", "/operations/nope", `{}`, self)
	if response.Code != http.StatusNotFound || strings.TrimSpace(response.Body.String()) != `{"detail":"Unknown operation"}` {
		t.Fatalf("%d %s", response.Code, response.Body)
	}
}

func TestReservedArgumentsAre403(t *testing.T) {
	f := newFixture(t)
	for _, key := range []string{"_person_pk", "_access", "_if_job_id"} {
		if response := f.do("POST", "/operations/access_context", `{"`+key+`":"x"}`, self); response.Code != http.StatusForbidden {
			t.Fatalf("%s: %d", key, response.Code)
		}
	}
}

func TestBodyMustBeAnObject(t *testing.T) {
	f := newFixture(t)
	for _, body := range []string{`[]`, `"x"`, `7`, `not json`} {
		if response := f.do("POST", "/operations/access_context", body, self); response.Code != http.StatusUnprocessableEntity {
			t.Fatalf("%s: %d %s", body, response.Code, response.Body)
		}
	}
}

func TestInternalOperationsNeedTheBackendAccount(t *testing.T) {
	f := newFixture(t)
	body := `{"issuer":"https://issuer","provider":"authentik","sub":"s1"}`
	if response := f.do("POST", "/operations/identity_resolve", body, nil); response.Code != http.StatusForbidden {
		t.Fatalf("anonymous: %d", response.Code)
	}
	response := f.do("POST", "/operations/identity_resolve", body, map[string]string{"X-PL-Source-Principal": backend})
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"created":true`) {
		t.Fatalf("backend: %d %s", response.Code, response.Body)
	}
	if !strings.Contains(response.Body.String(), `"pk":"person_00000000000000000000000000000001`[:20]) {
		t.Fatalf("new persons are person_<hex>: %s", response.Body)
	}
}

func TestPersonOperationsRequireAnAuthenticatedPerson(t *testing.T) {
	f := newFixture(t)
	if response := f.do("POST", "/operations/settings_get", `{}`, map[string]string{"X-Athlete-Pk": "person_a"}); response.Code != http.StatusForbidden {
		t.Fatalf("signed out: %d", response.Code)
	}
	if response := f.do("POST", "/operations/settings_get", `{}`, self); response.Code != http.StatusOK {
		t.Fatalf("self: %d %s", response.Code, response.Body)
	}
}

func TestPublicProfileSearchWorksSignedOut(t *testing.T) {
	f := newFixture(t)
	f.env.Seed("if-user", value.Item{"pk": "person_pub", "mapped_pk": "person_pub", "username": "person_pub", "nickname": "pubby", "display_name": "Pubby", "roles": []any{"athlete"}, "profile_visibility": "public"})
	response := f.do("POST", "/operations/profile_search", `{}`, nil)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"nickname":"pubby"`) || strings.Contains(response.Body.String(), `"alpha"`) {
		t.Fatalf("%d %s", response.Code, response.Body)
	}
}

func rpc(t *testing.T, f *fixture, headers map[string]string, body string) map[string]any {
	t.Helper()
	response := f.do("POST", "/mcp", body, headers)
	var decoded map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("%d %s", response.Code, response.Body)
	}
	return decoded
}

func TestMCPInitializeListAndCall(t *testing.T) {
	f := newFixture(t)
	initialize := rpc(t, f, nil, `{"jsonrpc":"2.0","id":1,"method":"initialize"}`)
	result, _ := initialize["result"].(map[string]any)
	if result["protocolVersion"] != "2025-03-26" {
		t.Fatalf("%v", initialize)
	}
	listed := rpc(t, f, nil, `{"jsonrpc":"2.0","id":2,"method":"tools/list"}`)
	tools, _ := listed["result"].(map[string]any)["tools"].([]any)
	names := map[string]bool{}
	for _, entry := range tools {
		names[entry.(map[string]any)["name"].(string)] = true
	}
	if !names["access_context"] || !names["profile_search"] || names["identity_resolve"] {
		t.Fatalf("internal-only tools must be hidden: %d tools", len(names))
	}
	if len(names) != 41 {
		t.Fatalf("expected 41 public tools, got %d", len(names))
	}
	called := rpc(t, f, self, `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"access_context","arguments":{}}}`)
	content, _ := called["result"].(map[string]any)
	if content["isError"] != false || content["structuredContent"] == nil {
		t.Fatalf("%v", called)
	}
	failed := rpc(t, f, nil, `{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"settings_get","arguments":{}}}`)
	if failure, _ := failed["result"].(map[string]any); failure["isError"] != true {
		t.Fatalf("%v", failed)
	}
	if missing := rpc(t, f, nil, `{"jsonrpc":"2.0","id":5,"method":"nope"}`); missing["error"] == nil {
		t.Fatalf("%v", missing)
	}
	if response := f.do("POST", "/mcp", `{"jsonrpc":"2.0","method":"notifications/initialized"}`, nil); response.Code != http.StatusAccepted {
		t.Fatalf("notification: %d", response.Code)
	}
}

func TestToolSchemasCarryTheScopedPrimaryKey(t *testing.T) {
	f := newFixture(t)
	listed := rpc(t, f, nil, `{"jsonrpc":"2.0","id":2,"method":"tools/list"}`)
	for _, entry := range listed["result"].(map[string]any)["tools"].([]any) {
		tool := entry.(map[string]any)
		properties, _ := tool["inputSchema"].(map[string]any)["properties"].(map[string]any)
		switch tool["name"] {
		case "note_list_private", "favorites", "notifications":
			if _, ok := properties["pk"]; !ok {
				t.Errorf("%s must expose the injected pk property", tool["name"])
			}
		case "access_context", "profile_get", "profile_search", "tag_catalog_get":
			if _, ok := properties["pk"]; ok {
				t.Errorf("%s is public and must not gain pk", tool["name"])
			}
		}
	}
}
