package serve

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/auth"
	"powerlifting/competition/internal/contract"
	"powerlifting/competition/internal/service"
	"powerlifting/competition/internal/store"
)

type access struct {
	extra map[string]any
	err   error
	calls int
}

func (a *access) Fetch(_ context.Context, _ string, _ map[string]any, _ auth.Caller) (map[string]any, error) {
	a.calls++
	if a.err != nil {
		return nil, a.err
	}
	result := map[string]any{"settings_pk": "person_1"}
	for key, value := range a.extra {
		result[key] = value
	}
	return result, nil
}

type env struct {
	handler http.Handler
	access  *access
	memory  *store.Memory
}

func newEnv(t *testing.T) *env {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	memory := store.NewMemory()
	memory.Load("health", []store.Item{
		{"pk": "athlete_1", "sk": "program#current", "ref_sk": "program#v001"},
		{"pk": "athlete_1", "sk": "program#v001", "operator_prefs": map[string]any{"attempt_jumps": map[string]any{"squat": map[string]any{"j1": 20, "j2": 20}}}, "current_maxes": map[string]any{"squat": 180}},
	})
	memory.Load("entries", []store.Item{
		{"pk": "athlete_1", "sk": "COMP#meet", "master_id": "meet", "name": "Meet", "start_date": "2027-05-01", "user_status": "confirmed", "entry_date": "2027-05-01", "block_id": "b1"},
		{"pk": "athlete_1", "sk": "COMP#other", "master_id": "other", "name": "Other", "start_date": "2027-06-01", "user_status": "available"},
	})
	probe := &access{}
	now := func() time.Time { return time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC) }
	svc, err := service.New(registry, probe, memory, memory, memory, now, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	return &env{handler: Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil))), access: probe, memory: memory}
}

var identity = map[string]string{"X-Person-Pk": "person_1", "X-Athlete-Pk": "athlete_1"}

func (e *env) do(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for name, value := range headers {
		request.Header.Set(name, value)
	}
	recorder := httptest.NewRecorder()
	e.handler.ServeHTTP(recorder, request)
	return recorder
}

func decode(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("not json: %q", recorder.Body.String())
	}
	return body
}

func TestSwaggerDocumentsEveryOperation(t *testing.T) {
	e := newEnv(t)
	registry, _ := contract.Load()
	if len(registry.All()) != 5 {
		t.Fatalf("expected the five competition operations, got %d", len(registry.All()))
	}
	document := decode(t, e.do(http.MethodGet, "/openapi.json", "", nil))
	paths := document["paths"].(map[string]any)
	for _, operation := range registry.All() {
		item, ok := paths["/operations/"+operation.Name].(map[string]any)
		if !ok {
			t.Fatalf("%s is not documented", operation.Name)
		}
		post := item["post"].(map[string]any)
		schema := post["requestBody"].(map[string]any)["content"].(map[string]any)["application/json"].(map[string]any)["schema"].(map[string]any)
		properties, _ := schema["properties"].(map[string]any)
		for name := range operation.InputSchema["properties"].(map[string]any) {
			if _, present := properties[name]; !present {
				t.Errorf("%s: request schema lacks %s", operation.Name, name)
			}
		}
		if _, present := post["responses"].(map[string]any)["200"]; !present {
			t.Errorf("%s: 200 response undocumented", operation.Name)
		}
	}
	for _, path := range []string{"/mcp", "/health"} {
		if _, present := paths[path]; !present {
			t.Errorf("%s is not documented", path)
		}
	}
	page := e.do(http.MethodGet, "/docs", "", nil).Body.String()
	if !strings.Contains(strings.ToLower(page), "swagger") || !strings.Contains(page, "/openapi") {
		t.Fatal("/docs must serve Swagger UI for the generated document")
	}
}

func TestHealth(t *testing.T) {
	e := newEnv(t)
	for _, path := range []string{"/health", "/healthz"} {
		recorder := e.do(http.MethodGet, path, "", nil)
		if body := decode(t, recorder); recorder.Code != http.StatusOK || body["status"] != "ok" || body["domain"] != "competition" {
			t.Fatalf("%s: %d %v", path, recorder.Code, body)
		}
	}
}

func TestResultsUsePythonJSONRendering(t *testing.T) {
	e := newEnv(t)
	recorder := e.do(http.MethodPost, "/operations/calculate_attempts", `{"lift":"squat","opener_kg":160}`, identity)
	want := `{"attempt_1_kg":160,"attempt_2_kg":180.0,"attempt_3_kg":200.0,"jumps_used":{"j1":20,"j2":20},"lift":"squat","warnings":["Attempt 3 (200.0kg) exceeds current max of 180kg — confirm this is a target PR."]}`
	if recorder.Code != http.StatusOK || recorder.Body.String() != want {
		t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
	}
	if contentType := recorder.Header().Get("Content-Type"); !strings.HasPrefix(contentType, "application/json") {
		t.Fatalf("content type %q", contentType)
	}
}

func TestListThroughHTTP(t *testing.T) {
	e := newEnv(t)
	recorder := e.do(http.MethodPost, "/operations/health_list_competitions", `{"op":"list"}`, identity)
	body := decode(t, recorder)
	list, _ := body["competitions"].([]any)
	if recorder.Code != http.StatusOK || len(list) != 2 {
		t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
	}
	if first := list[0].(map[string]any); first["master_id"] != "meet" || first["units"] != "kg" {
		t.Fatalf("unexpected first entry %v", first)
	}
}

func TestUpdateWritesAndBumpsTheAnalysisVersion(t *testing.T) {
	e := newEnv(t)
	recorder := e.do(http.MethodPost, "/operations/health_update_user_competition", `{"master_id":"meet","patch":{"notes":"hello","weight_class_kg":93.0}}`, identity)
	body := decode(t, recorder)
	if recorder.Code != http.StatusOK || body["notes"] != "hello" || body["updated_at"] != "2026-11-14T12:00:00+00:00" {
		t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
	}
	if !strings.Contains(recorder.Body.String(), `"weight_class_kg":93.0`) {
		t.Fatalf("float rendering lost: %s", recorder.Body.String())
	}
	if e.memory.Bumps["pl:analysis-version:athlete_1"] != 1 {
		t.Fatalf("bumps %v", e.memory.Bumps)
	}
	if stored := e.memory.EntryItems[[2]string{"athlete_1", "COMP#meet"}]; stored["notes"] != "hello" {
		t.Fatalf("not persisted: %v", stored)
	}
}

func TestRejections(t *testing.T) {
	e := newEnv(t)
	cases := []struct {
		name    string
		path    string
		body    string
		headers map[string]string
		status  int
		check   func(map[string]any) bool
	}{
		{"unknown operation", "/operations/nope", `{}`, identity, 404, func(b map[string]any) bool { return b["detail"] == "Unknown operation" }},
		{"reserved argument", "/operations/health_list_competitions", `{"_access":{}}`, identity, 403, func(b map[string]any) bool { return detailCode(b) == "forbidden" }},
		{"foreign athlete", "/operations/health_list_competitions", `{"pk":"someone_else"}`, identity, 403, func(b map[string]any) bool { return detailCode(b) == "forbidden" }},
		{"no athlete", "/operations/health_list_competitions", `{}`, map[string]string{"X-Person-Pk": "person_1"}, 403, func(b map[string]any) bool { return detailCode(b) == "forbidden" }},
		{"schema violation", "/operations/calculate_attempts", `{"lift":"snatch","opener_kg":100}`, identity, 422, func(b map[string]any) bool { return detailCode(b) == "validation" }},
		{"domain validation", "/operations/health_update_user_competition", `{"master_id":"meet","patch":{"bogus":1}}`, identity, 422, func(b map[string]any) bool {
			return b["detail"].(map[string]any)["message"] == "competition fields are not editable: bogus"
		}},
		{"missing entry", "/operations/health_update_user_competition", `{"master_id":"gone","patch":{"notes":"x"}}`, identity, 422, func(b map[string]any) bool {
			return b["detail"].(map[string]any)["message"] == "Competition not found: gone"
		}},
		{"body is not an object", "/operations/calculate_attempts", `[1]`, identity, 422, func(b map[string]any) bool { return b["detail"] != nil }},
		{"generation without turn", "/operations/health_list_competitions", `{}`, map[string]string{"X-Person-Pk": "p", "X-Athlete-Pk": "athlete_1", "X-If-Generation-Id": "g1"}, 403, func(b map[string]any) bool {
			return b["detail"] == "Generation requires an active native turn"
		}},
		{"nested without execution", "/operations/health_list_competitions", `{}`, map[string]string{"X-Person-Pk": "p", "X-Athlete-Pk": "athlete_1", "X-PL-Nested-Operation": "true"}, 409, func(b map[string]any) bool { return detailCode(b) == "uncertain" }},
		{"program missing", "/operations/calculate_attempts", `{"lift":"squat","opener_kg":100}`, map[string]string{"X-Person-Pk": "p", "X-Athlete-Pk": "athlete_2"}, 404, func(b map[string]any) bool { return detailCode(b) == "not_found" }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			recorder := e.do(http.MethodPost, tc.path, tc.body, tc.headers)
			body := decode(t, recorder)
			if recorder.Code != tc.status || !tc.check(body) {
				t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
			}
		})
	}
}

func detailCode(body map[string]any) string {
	detail, _ := body["detail"].(map[string]any)
	code, _ := detail["code"].(string)
	return code
}

func TestAccessDenialAndOutageAreForwarded(t *testing.T) {
	e := newEnv(t)
	e.access.err = apperr.AccessDenied(http.StatusForbidden)
	recorder := e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, identity)
	if recorder.Code != http.StatusForbidden || detailCode(decode(t, recorder)) != "forbidden" {
		t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
	}
	e.access.err = apperr.AccessUnavailable()
	recorder = e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, identity)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
	}
	e.access.err = errors.New("boom")
	if recorder = e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, identity); recorder.Code != http.StatusInternalServerError {
		t.Fatalf("%d", recorder.Code)
	}
}

func TestScopedAccessHidesOtherEntries(t *testing.T) {
	e := newEnv(t)
	e.access.extra = map[string]any{"is_self": false, "competition_scope": map[string]any{"read": []any{"COMP#other"}, "write": []any{}}}
	body := decode(t, e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, identity))
	list := body["competitions"].([]any)
	if len(list) != 1 || list[0].(map[string]any)["master_id"] != "other" {
		t.Fatalf("%v", list)
	}
}

func TestJobCallsAreWrapped(t *testing.T) {
	e := newEnv(t)
	headers := map[string]string{"X-Person-Pk": "p", "X-Athlete-Pk": "athlete_1", "X-If-Turn-Id": "turn_1"}
	body := decode(t, e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, headers))
	if body["status"] != "succeeded" || body["result"] == nil {
		t.Fatalf("%v", body)
	}
	headers["X-PL-Nested-Operation"] = "true"
	body = decode(t, e.do(http.MethodPost, "/operations/health_list_competitions", `{}`, headers))
	if body["competitions"] == nil {
		t.Fatalf("nested results are returned bare: %v", body)
	}
}

func TestMCP(t *testing.T) {
	e := newEnv(t)
	call := func(payload string) map[string]any {
		recorder := e.do(http.MethodPost, "/mcp", payload, identity)
		if recorder.Code != http.StatusOK {
			t.Fatalf("%d %s", recorder.Code, recorder.Body.String())
		}
		return decode(t, recorder)
	}
	initialised := call(`{"jsonrpc":"2.0","id":1,"method":"initialize"}`)["result"].(map[string]any)
	if initialised["protocolVersion"] != "2025-03-26" || initialised["serverInfo"].(map[string]any)["name"] != "powerlifting-competition" {
		t.Fatalf("%v", initialised)
	}
	listed := call(`{"jsonrpc":"2.0","id":2,"method":"tools/list"}`)["result"].(map[string]any)["tools"].([]any)
	if len(listed) != 5 {
		t.Fatalf("%d tools", len(listed))
	}
	for _, raw := range listed {
		tool := raw.(map[string]any)
		if tool["inputSchema"] == nil || tool["outputSchema"] == nil || tool["description"] == "" {
			t.Fatalf("incomplete tool %v", tool)
		}
	}
	good := call(`{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"calculate_attempts","arguments":{"lift":"squat","opener_kg":160}}}`)["result"].(map[string]any)
	if good["isError"] != false || good["structuredContent"].(map[string]any)["attempt_3_kg"] != 200.0 {
		t.Fatalf("%v", good)
	}
	text := good["content"].([]any)[0].(map[string]any)["text"].(string)
	if !strings.Contains(text, `"attempt_2_kg": 180.0`) || !strings.Contains(text, `\u2014`) {
		t.Fatalf("tool text is not rendered like Python json.dumps: %s", text)
	}
	bad := call(`{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"nope","arguments":{}}}`)["result"].(map[string]any)
	if bad["isError"] != true || !strings.Contains(bad["content"].([]any)[0].(map[string]any)["text"].(string), `"status": 404`) {
		t.Fatalf("%v", bad)
	}
	if method := call(`{"jsonrpc":"2.0","id":5,"method":"resources/list"}`); method["error"].(map[string]any)["code"] != -32601.0 {
		t.Fatalf("%v", method)
	}
	if recorder := e.do(http.MethodPost, "/mcp", `{"jsonrpc":"2.0","method":"notifications/initialized"}`, identity); recorder.Code != http.StatusAccepted {
		t.Fatalf("notification: %d", recorder.Code)
	}
}
