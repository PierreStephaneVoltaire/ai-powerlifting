package serve

import (
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

	"powerlifting/sessions/internal/auth"
	"powerlifting/sessions/internal/contract"
	"powerlifting/sessions/internal/service"
	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/store"
	"powerlifting/sessions/internal/value"
)

type profile struct {
	*httptest.Server
	mu     sync.Mutex
	hits   int
	status int
	body   string
}

func newProfile(t *testing.T, status int, body string) *profile {
	t.Helper()
	p := &profile{status: status, body: body}
	p.Server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p.mu.Lock()
		p.hits++
		p.mu.Unlock()
		w.WriteHeader(p.status)
		_, _ = w.Write([]byte(p.body))
	}))
	t.Cleanup(p.Close)
	return p
}

func (p *profile) count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.hits
}

type bumps struct {
	mu   sync.Mutex
	keys []string
}

func (b *bumps) Bump(_ context.Context, athlete string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.keys = append(b.keys, store.VersionKey(athlete))
}

type env struct {
	handler http.Handler
	profile *profile
	memory  *store.Memory
	bumps   *bumps
}

func newEnv(t *testing.T, profileStatus int) *env {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	e := &env{profile: newProfile(t, profileStatus, `{"settings_pk":"person_1","athlete_pk":"athlete_1","is_self":true}`), memory: store.NewMemory(), bumps: &bumps{}}
	e.memory.SeedHealth(value.Item{"pk": "athlete_1", "sk": "program#current", "ref_sk": "program#v001"})
	e.memory.SeedHealth(value.Item{"pk": "athlete_1", "sk": "program#v001", "phases": []any{}})
	counter := 0
	sessions := &session.Service{
		Sessions: e.memory, Programs: e.memory, SourceTable: "if-health",
		Now:   func() time.Time { return time.Unix(0, 0) },
		NewID: func() string { counter++; return "id-" + string(value.Int(counter)) },
	}
	svc, err := service.New(registry, auth.NewAccess(e.profile.URL), sessions, e.bumps)
	if err != nil {
		t.Fatal(err)
	}
	e.handler = Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	return e
}

func (e *env) do(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for name, v := range headers {
		request.Header.Set(name, v)
	}
	recorder := httptest.NewRecorder()
	e.handler.ServeHTTP(recorder, request)
	return recorder
}

var identity = map[string]string{"X-Person-Pk": "person_1", "X-Athlete-Pk": "athlete_1"}

func with(extra map[string]string) map[string]string {
	merged := map[string]string{}
	for name, v := range identity {
		merged[name] = v
	}
	for name, v := range extra {
		merged[name] = v
	}
	return merged
}

const createBody = `{"session":{"date":"2026-09-14","week_number":1,"exercises":[{"name":"Squat","sets":2,"kg":100.0}]}}`

func TestUnknownOperationIs404BeforeAccess(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, identity)
	if response.Code != http.StatusNotFound || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d body %s", response.Code, e.profile.count(), response.Body)
	}
	if strings.TrimSpace(response.Body.String()) != `{"detail":"Unknown operation"}` {
		t.Fatalf("body %s", response.Body)
	}
}

func TestGenerationWithoutTurnIs403BeforeEverything(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, with(map[string]string{"X-If-Generation-Id": "gen_1"}))
	if response.Code != http.StatusForbidden || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d", response.Code, e.profile.count())
	}
}

func TestReservedArgumentsAre403BeforeAccess(t *testing.T) {
	e := newEnv(t, 200)
	for _, key := range []string{"_person_pk", "_access", "_if_job_id"} {
		if response := e.do("POST", "/operations/session_list", `{"`+key+`":"x"}`, identity); response.Code != http.StatusForbidden {
			t.Fatalf("%s: status %d", key, response.Code)
		}
	}
	if e.profile.count() != 0 {
		t.Fatalf("access called %d times", e.profile.count())
	}
}

func TestMissingPersonIs403WithoutAccessCall(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/session_list", `{}`, map[string]string{"X-Athlete-Pk": "athlete_1"})
	if response.Code != http.StatusForbidden || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d", response.Code, e.profile.count())
	}
}

func TestMissingAthleteIs403(t *testing.T) {
	e := newEnv(t, 200)
	if response := e.do("POST", "/operations/session_list", `{}`, map[string]string{"X-Person-Pk": "person_1"}); response.Code != http.StatusForbidden {
		t.Fatalf("status %d", response.Code)
	}
}

func TestConflictingPkIs403AndPkIsForcedToAthlete(t *testing.T) {
	e := newEnv(t, 200)
	if response := e.do("POST", "/operations/session_list", `{"pk":"someone_else"}`, identity); response.Code != http.StatusForbidden {
		t.Fatalf("status %d", response.Code)
	}
	if response := e.do("POST", "/operations/session_list", `{}`, identity); response.Code != http.StatusOK {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
}

func TestDeniedAccessIsForwardedAndUnreachableIs503(t *testing.T) {
	e := newEnv(t, 403)
	if response := e.do("POST", "/operations/session_list", `{}`, identity); response.Code != http.StatusForbidden {
		t.Fatalf("status %d", response.Code)
	}
	e.profile.Close()
	if response := e.do("POST", "/operations/session_list", `{}`, identity); response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", response.Code)
	}
}

func TestInputValidationIs422(t *testing.T) {
	e := newEnv(t, 200)
	for _, body := range []string{`{}`, `{"session":"nope"}`} {
		if response := e.do("POST", "/operations/session_create", body, identity); response.Code != http.StatusUnprocessableEntity {
			t.Fatalf("%s: status %d", body, response.Code)
		}
	}
	if response := e.do("POST", "/operations/session_patch", `{"date":"2026-09-13","patch":{}}`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("missing index: status %d", response.Code)
	}
	if response := e.do("POST", "/operations/session_replace_all", `{}`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status %d", response.Code)
	}
}

func TestBodyMustBeAnObject(t *testing.T) {
	e := newEnv(t, 200)
	for _, body := range []string{`[]`, `null`, `nonsense`} {
		if response := e.do("POST", "/operations/session_list", body, identity); response.Code != http.StatusUnprocessableEntity {
			t.Fatalf("%q: status %d", body, response.Code)
		}
	}
}

func TestCreateKeepsPythonNumberFormatAndBumpsAnalysisVersion(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/session_create", createBody, identity)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
	var created map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(response.Body.String(), `"kg":100.0`) {
		t.Fatalf("float literal lost: %s", response.Body)
	}
	if created["id"] != "id-1" || created["phase_name"] != "Unscheduled" {
		t.Fatalf("created %v", created)
	}
	if len(e.bumps.keys) != 1 || e.bumps.keys[0] != "pl:analysis-version:athlete_1" {
		t.Fatalf("bumps %v", e.bumps.keys)
	}
	list := e.do("POST", "/operations/session_list", `{}`, identity)
	if list.Code != http.StatusOK || len(e.bumps.keys) != 1 {
		t.Fatalf("read bumped version: %d %v", list.Code, e.bumps.keys)
	}
}

func TestFailedWriteDoesNotBumpAnalysisVersion(t *testing.T) {
	e := newEnv(t, 200)
	if response := e.do("POST", "/operations/session_create", `{"session":{}}`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status %d", response.Code)
	}
	if len(e.bumps.keys) != 0 {
		t.Fatalf("bumps %v", e.bumps.keys)
	}
}

func TestIdentityConflictIs409WithCode(t *testing.T) {
	e := newEnv(t, 200)
	body := `{"session":{"id":"same","date":"2026-09-14"}}`
	if response := e.do("POST", "/operations/session_create", body, identity); response.Code != http.StatusOK {
		t.Fatalf("status %d", response.Code)
	}
	response := e.do("POST", "/operations/session_create", body, identity)
	if response.Code != http.StatusConflict || !strings.Contains(response.Body.String(), `"code":"session_identity_conflict"`) {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
}

func TestActiveJobWrapsDeterministicResult(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/session_list", `{}`, with(map[string]string{"X-If-Turn-Id": "turn_1"}))
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"status":"succeeded"`) {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
	nested := e.do("POST", "/operations/session_list", `{}`, with(map[string]string{"X-If-Turn-Id": "turn_1", "X-PL-Nested-Operation": "true"}))
	if strings.Contains(nested.Body.String(), `"status":"succeeded"`) {
		t.Fatalf("nested result wrapped: %s", nested.Body)
	}
	orphan := e.do("POST", "/operations/session_list", `{}`, with(map[string]string{"X-PL-Nested-Operation": "true"}))
	if orphan.Code != http.StatusConflict {
		t.Fatalf("status %d", orphan.Code)
	}
}

func TestPublishedViewHidesVideosAndWeightForOtherViewers(t *testing.T) {
	e := newEnv(t, 200)
	e.profile.body = `{"settings_pk":"viewer","athlete_pk":"athlete_1","is_self":false,"permissions":["sessions:read"],"granted_permissions":["sessions:read"]}`
	e.memory.SeedSession(value.Item{"pk": "athlete_1", "sk": "session#program#v001#2026-09-14#001#a", "session_id": "a", "date": "2026-09-14", "program_sk": "program#v001", "body_weight_kg": 80, "videos": []any{map[string]any{"video_id": "v"}}})
	response := e.do("POST", "/operations/session_get", `{"date":"2026-09-14","index":0}`, identity)
	if response.Code != http.StatusOK || strings.Contains(response.Body.String(), "videos") || strings.Contains(response.Body.String(), "body_weight_kg") {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
}

func TestHealthAndDocs(t *testing.T) {
	e := newEnv(t, 200)
	for _, path := range []string{"/health", "/healthz"} {
		response := e.do("GET", path, "", nil)
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"domain":"sessions"`) {
			t.Fatalf("%s: %d %s", path, response.Code, response.Body)
		}
	}
	page := e.do("GET", "/docs", "", nil).Body.String()
	if !strings.Contains(strings.ToLower(page), "swagger") || !strings.Contains(page, "/openapi") {
		t.Fatal("/docs must serve Swagger UI for the generated document")
	}
}

func TestSwaggerDocumentsEveryOperationWithHeaders(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("GET", "/openapi.json", "", nil)
	if response.Code != http.StatusOK {
		t.Fatalf("openapi.json: %d", response.Code)
	}
	var document map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &document); err != nil {
		t.Fatal(err)
	}
	registry, _ := contract.Load()
	if len(registry.All()) != 10 {
		t.Fatalf("expected the ten sessions operations, got %d", len(registry.All()))
	}
	paths := document["paths"].(map[string]any)
	wantHeaders := []string{"X-Person-Pk", "X-Athlete-Pk", "X-PL-Source-Principal", "X-If-Job-Id", "X-If-Turn-Id", "X-PL-Nested-Operation", "X-If-Generation-Id", "X-If-Generation-Attempt"}
	for _, operation := range registry.All() {
		item, ok := paths["/operations/"+operation.Name].(map[string]any)
		if !ok {
			t.Errorf("%s is not documented", operation.Name)
			continue
		}
		post, ok := item["post"].(map[string]any)
		if !ok {
			t.Errorf("%s lacks a POST", operation.Name)
			continue
		}
		documented := map[string]bool{}
		for _, parameter := range post["parameters"].([]any) {
			entry := parameter.(map[string]any)
			if entry["in"] == "header" {
				documented[strings.ToLower(entry["name"].(string))] = true
			}
		}
		for _, name := range wantHeaders {
			if !documented[strings.ToLower(name)] {
				t.Errorf("%s lacks header parameter %s", operation.Name, name)
			}
		}
		body := post["requestBody"].(map[string]any)["content"].(map[string]any)["application/json"].(map[string]any)["schema"].(map[string]any)
		properties, _ := body["properties"].(map[string]any)
		for name := range operation.InputSchema["properties"].(map[string]any) {
			if _, present := properties[name]; !present {
				t.Errorf("%s: request schema lacks %s", operation.Name, name)
			}
		}
		if _, present := post["responses"].(map[string]any)["200"]; !present {
			t.Errorf("%s: response 200 undocumented", operation.Name)
		}
	}
	for _, path := range []string{"/mcp", "/health"} {
		if _, ok := paths[path]; !ok {
			t.Errorf("%s is not documented", path)
		}
	}
}

func rpc(t *testing.T, e *env, body string) map[string]any {
	t.Helper()
	response := e.do("POST", "/mcp", body, identity)
	var out map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &out); err != nil {
		t.Fatalf("%v: %s", err, response.Body)
	}
	return out
}

func TestMCPListsAndCallsTools(t *testing.T) {
	e := newEnv(t, 200)
	listed := rpc(t, e, `{"jsonrpc":"2.0","id":1,"method":"tools/list"}`)["result"].(map[string]any)["tools"].([]any)
	if len(listed) != 10 {
		t.Fatalf("tools %d", len(listed))
	}
	called := rpc(t, e, `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"session_list","arguments":{"limit":5}}}`)["result"].(map[string]any)
	if called["isError"] != false || called["structuredContent"] == nil {
		t.Fatalf("call %v", called)
	}
	failed := rpc(t, e, `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"session_create","arguments":{"session":{"id":"x","date":"2026-01-01"}}}}`)["result"].(map[string]any)
	again := rpc(t, e, `{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"session_create","arguments":{"session":{"id":"x","date":"2026-01-01"}}}}`)["result"].(map[string]any)
	if failed["isError"] != false || again["isError"] != true || !strings.Contains(again["content"].([]any)[0].(map[string]any)["text"].(string), "session_identity_conflict") {
		t.Fatalf("failed %v again %v", failed, again)
	}
	if notification := e.do("POST", "/mcp", `{"jsonrpc":"2.0","method":"notifications/initialized"}`, identity); notification.Code != http.StatusAccepted {
		t.Fatalf("notification %d", notification.Code)
	}
	unknown := rpc(t, e, `{"jsonrpc":"2.0","id":5,"method":"nope"}`)
	if unknown["error"].(map[string]any)["code"] != float64(-32601) {
		t.Fatalf("unknown %v", unknown)
	}
}
