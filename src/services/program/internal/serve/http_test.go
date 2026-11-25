package serve

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"powerlifting/program/internal/analysis"
	"powerlifting/program/internal/auth"
	"powerlifting/program/internal/contract"
	"powerlifting/program/internal/env"
	"powerlifting/program/internal/ops"
	"powerlifting/program/internal/service"
	"powerlifting/program/internal/store"
)

type profileHit struct {
	headers http.Header
	body    map[string]any
}

type profile struct {
	*httptest.Server
	mu     sync.Mutex
	hits   []profileHit
	status int
}

func newProfile(t *testing.T, status int) *profile {
	t.Helper()
	p := &profile{status: status}
	p.Server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		p.mu.Lock()
		p.hits = append(p.hits, profileHit{headers: r.Header.Clone(), body: body})
		p.mu.Unlock()
		w.WriteHeader(p.status)
		_, _ = w.Write([]byte(`{"settings_pk":"person_1","is_self":true}`))
	}))
	t.Cleanup(p.Close)
	return p
}

func (p *profile) count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.hits)
}

type noAnalytics struct{}

func (noAnalytics) WeeklyAnalysis(context.Context, ops.Caller, map[string]any) (*ops.Weekly, error) {
	return nil, io.EOF
}

type bumps struct{ operations []string }

func (b *bumps) Record(_ context.Context, operation, _ string) {
	b.operations = append(b.operations, operation)
}

var _ analysis.Versions = (*bumps)(nil)

type environment struct {
	handler http.Handler
	profile *profile
	db      *store.Memory
	bumps   *bumps
}

func newEnvironment(t *testing.T, profileStatus int) *environment {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	tables := store.Tables{Health: "h", Sessions: "s", Supplements: "sup", Competitions: "c", Templates: "t"}
	db := store.NewMemory()
	runtimeEnv := env.Env{Now: func() time.Time { return time.Unix(0, 0).UTC() }, UUID: func() string { return "00000000-0000-4000-8000-000000000000" }}
	e := &environment{profile: newProfile(t, profileStatus), db: db, bumps: &bumps{}}
	deps := &ops.Deps{
		Programs: store.New(db, tables, runtimeEnv), Related: store.Related{DB: db, Tables: tables}, Analytics: noAnalytics{},
		Env: runtimeEnv, Config: ops.Config{TemplatesLibraryPK: "lib"}, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Today: func() string { return "2026-01-01" },
	}
	svc, err := service.New(registry, auth.NewAccess(e.profile.URL), deps, e.bumps)
	if err != nil {
		t.Fatal(err)
	}
	e.handler = Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	return e
}

func (e *environment) do(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for name, value := range headers {
		request.Header.Set(name, value)
	}
	recorder := httptest.NewRecorder()
	e.handler.ServeHTTP(recorder, request)
	return recorder
}

var identity = map[string]string{"X-Person-Pk": "person_1", "X-Athlete-Pk": "athlete_1"}

func with(extra map[string]string) map[string]string {
	merged := map[string]string{}
	for name, value := range identity {
		merged[name] = value
	}
	for name, value := range extra {
		merged[name] = value
	}
	return merged
}

func TestUnknownOperationIs404BeforeAccess(t *testing.T) {
	e := newEnvironment(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, identity)
	if response.Code != http.StatusNotFound || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d body %s", response.Code, e.profile.count(), response.Body)
	}
}

func TestGenerationWithoutJobIs403BeforeEverything(t *testing.T) {
	e := newEnvironment(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, with(map[string]string{"X-If-Generation-Id": "gen_1"}))
	if response.Code != http.StatusForbidden || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d", response.Code, e.profile.count())
	}
}

func TestReservedArgumentsAre403BeforeAccess(t *testing.T) {
	e := newEnvironment(t, 200)
	for _, key := range []string{"_person_pk", "_access", "_if_job_id"} {
		response := e.do("POST", "/operations/health_setup_status", `{"`+key+`":"x"}`, identity)
		if response.Code != http.StatusForbidden {
			t.Fatalf("%s: status %d", key, response.Code)
		}
	}
	if e.profile.count() != 0 {
		t.Fatalf("access called %d times", e.profile.count())
	}
}

func TestMissingAthleteIs403(t *testing.T) {
	e := newEnvironment(t, 200)
	response := e.do("POST", "/operations/health_setup_status", `{}`, map[string]string{"X-Person-Pk": "person_1"})
	if response.Code != http.StatusForbidden {
		t.Fatalf("status %d", response.Code)
	}
}

func TestAccessContextReceivesOperationArgumentsAndIdentity(t *testing.T) {
	e := newEnvironment(t, 200)
	e.do("POST", "/operations/health_setup_status", `{}`, identity)
	hit := e.profile.hits[0]
	if hit.headers.Get("X-Person-Pk") != "person_1" || hit.headers.Get("X-Athlete-Pk") != "athlete_1" || hit.body["operation"] != "health_setup_status" {
		t.Fatalf("hit %v", hit)
	}
}

func TestDeniedAccessIs403AndUnreachableIs503(t *testing.T) {
	e := newEnvironment(t, 403)
	if response := e.do("POST", "/operations/health_setup_status", `{}`, identity); response.Code != http.StatusForbidden {
		t.Fatalf("status %d", response.Code)
	}
	e = newEnvironment(t, 200)
	e.profile.Close()
	if response := e.do("POST", "/operations/health_setup_status", `{}`, identity); response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", response.Code)
	}
}

func TestPkConflictIs403ValidationIs422(t *testing.T) {
	e := newEnvironment(t, 200)
	if response := e.do("POST", "/operations/health_setup_status", `{"pk":"someone_else"}`, identity); response.Code != http.StatusForbidden {
		t.Fatalf("conflict %d", response.Code)
	}
	if response := e.do("POST", "/operations/block_transition", `{"action":"explode","block_id":"x"}`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("validation %d", response.Code)
	}
	if response := e.do("POST", "/operations/health_setup_status", `[]`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("body %d", response.Code)
	}
}

func TestSetupThenStatusThroughHTTPBumpsAnalysisVersion(t *testing.T) {
	e := newEnvironment(t, 200)
	body := `{"mode":"blank","start_date":"2026-12-07","week_start_day":"Monday","maxes":{"squat":150.5}}`
	response := e.do("POST", "/operations/health_setup_initialize", body, identity)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
	var result map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &result)
	if result["status"] != "initialized" || result["sessionCount"].(float64) != 0 {
		t.Fatalf("result %v", result)
	}
	status := e.do("POST", "/operations/health_setup_status", `{}`, identity)
	var state map[string]any
	_ = json.Unmarshal(status.Body.Bytes(), &state)
	if state["hasCurrentProgram"] != true || state["mapped_pk"] != "athlete_1" {
		t.Fatalf("state %v", state)
	}
	if len(e.bumps.operations) != 2 {
		t.Fatalf("bumps %v", e.bumps.operations)
	}
	again := e.do("POST", "/operations/health_setup_initialize", body, identity)
	if again.Code != http.StatusUnprocessableEntity || !strings.Contains(again.Body.String(), "ALREADY_INITIALIZED") {
		t.Fatalf("second init %d %s", again.Code, again.Body)
	}
}

func TestJobWrapsResultUnlessNested(t *testing.T) {
	e := newEnvironment(t, 200)
	response := e.do("POST", "/operations/health_invalidate_program_cache", `{}`, with(map[string]string{"X-If-Turn-Id": "turn_1"}))
	var wrapped map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &wrapped)
	if wrapped["status"] != "succeeded" || wrapped["result"].(map[string]any)["success"] != true {
		t.Fatalf("wrapped %v", wrapped)
	}
	nested := e.do("POST", "/operations/health_invalidate_program_cache", `{}`, with(map[string]string{"X-If-Turn-Id": "turn_1", "X-PL-Nested-Operation": "true"}))
	var plain map[string]any
	_ = json.Unmarshal(nested.Body.Bytes(), &plain)
	if plain["success"] != true {
		t.Fatalf("nested %v", plain)
	}
	orphan := e.do("POST", "/operations/health_invalidate_program_cache", `{}`, with(map[string]string{"X-PL-Nested-Operation": "true"}))
	if orphan.Code != http.StatusConflict {
		t.Fatalf("orphan nested %d", orphan.Code)
	}
}

func TestSwaggerDocumentsEveryOperation(t *testing.T) {
	e := newEnvironment(t, 200)
	response := e.do("GET", "/openapi.json", "", nil)
	var document map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &document); err != nil {
		t.Fatal(err)
	}
	paths := document["paths"].(map[string]any)
	registry, _ := contract.Load()
	if len(registry.All()) != 16 {
		t.Fatalf("expected 16 operations, got %d", len(registry.All()))
	}
	wantHeaders := []string{"X-Person-Pk", "X-Athlete-Pk", "X-PL-Source-Principal", "X-If-Job-Id", "X-If-Turn-Id", "X-PL-Nested-Operation"}
	for _, operation := range registry.All() {
		item, ok := paths["/operations/"+operation.Name].(map[string]any)
		if !ok {
			t.Errorf("%s undocumented", operation.Name)
			continue
		}
		post := item["post"].(map[string]any)
		documented := map[string]bool{}
		for _, parameter := range post["parameters"].([]any) {
			entry := parameter.(map[string]any)
			if entry["in"] == "header" {
				documented[strings.ToLower(entry["name"].(string))] = true
			}
		}
		for _, name := range wantHeaders {
			if !documented[strings.ToLower(name)] {
				t.Errorf("%s lacks header %s", operation.Name, name)
			}
		}
		if _, present := post["requestBody"]; !present {
			t.Errorf("%s lacks a request body schema", operation.Name)
		}
		if _, present := post["responses"].(map[string]any)["200"]; !present {
			t.Errorf("%s lacks a 200 response", operation.Name)
		}
	}
	for _, path := range []string{"/mcp", "/health", "/healthz"} {
		if _, ok := paths[path]; !ok {
			t.Errorf("%s undocumented", path)
		}
	}
	page := e.do("GET", "/docs", "", nil).Body.String()
	if !strings.Contains(strings.ToLower(page), "swagger") || !strings.Contains(page, "/openapi") {
		t.Fatal("/docs must serve Swagger UI")
	}
}

func TestTemplateApplySessionsRequiresTemplatesWorkload(t *testing.T) {
	e := newEnvironment(t, 200)
	for _, source := range []string{"", "spiffe://cluster.local/ns/powerlifting/sa/pl-imports", "spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend"} {
		response := e.do("POST", "/operations/template_apply_sessions", `{}`, with(map[string]string{"X-PL-Source-Principal": source}))
		if response.Code != http.StatusForbidden {
			t.Fatalf("source %q: status %d body %s", source, response.Code, response.Body.String())
		}
	}
	response := e.do("POST", "/operations/template_apply_sessions", `{}`, with(map[string]string{"X-PL-Source-Principal": "spiffe://cluster.local/ns/powerlifting/sa/pl-templates"}))
	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("templates workload: status %d body %s", response.Code, response.Body.String())
	}
}

func TestSessionImportRequiresImportsWorkload(t *testing.T) {
	e := newEnvironment(t, 200)
	for _, source := range []string{"", "spiffe://cluster.local/ns/powerlifting/sa/pl-templates", "spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend"} {
		response := e.do("POST", "/operations/program_apply_session_import", `{}`, with(map[string]string{"X-PL-Source-Principal": source}))
		if response.Code != http.StatusForbidden {
			t.Fatalf("source %q: status %d body %s", source, response.Code, response.Body.String())
		}
	}
	response := e.do("POST", "/operations/program_apply_session_import", `{}`, with(map[string]string{"X-PL-Source-Principal": "spiffe://cluster.local/ns/powerlifting/sa/pl-imports"}))
	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("imports workload: status %d body %s", response.Code, response.Body.String())
	}
}

func TestHealthProbes(t *testing.T) {
	e := newEnvironment(t, 200)
	for _, path := range []string{"/health", "/healthz"} {
		var body map[string]any
		response := e.do("GET", path, "", nil)
		_ = json.Unmarshal(response.Body.Bytes(), &body)
		if response.Code != http.StatusOK || body["status"] != "ok" || body["domain"] != "program" {
			t.Fatalf("%s: %d %v", path, response.Code, body)
		}
	}
}

func TestMCPToolsListAndCall(t *testing.T) {
	e := newEnvironment(t, 200)
	call := func(payload string) map[string]any {
		response := e.do("POST", "/mcp", payload, identity)
		var decoded map[string]any
		_ = json.Unmarshal(bytes.TrimSpace(response.Body.Bytes()), &decoded)
		return decoded
	}
	listed := call(`{"jsonrpc":"2.0","id":1,"method":"tools/list"}`)["result"].(map[string]any)["tools"].([]any)
	if len(listed) == 0 || len(listed) > 18 {
		t.Fatalf("tools %d", len(listed))
	}
	result := call(`{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_setup_status","arguments":{}}}`)["result"].(map[string]any)
	if result["isError"] != false || result["structuredContent"].(map[string]any)["needsSetup"] != true {
		t.Fatalf("call %v", result)
	}
	failure := call(`{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"nope","arguments":{}}}`)["result"].(map[string]any)
	if failure["isError"] != true {
		t.Fatalf("failure %v", failure)
	}
	if call(`{"jsonrpc":"2.0","id":4,"method":"unknown"}`)["error"] == nil {
		t.Fatal("unknown method accepted")
	}
}
