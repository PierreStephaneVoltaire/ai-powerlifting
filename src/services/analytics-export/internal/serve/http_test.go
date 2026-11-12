package serve

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/contract"
	"powerlifting/analytics-export/internal/data"
	"powerlifting/analytics-export/internal/service"
	"powerlifting/analytics-export/internal/store"
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
		if r.URL.Path != "/operations/access_context" || r.Method != http.MethodPost {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(p.status)
		_, _ = w.Write([]byte(`{"settings_pk":"person_1"}`))
	}))
	t.Cleanup(p.Close)
	return p
}

func (p *profile) count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.hits)
}

type fakeBundles struct {
	bundle map[string]any
	err    error
	calls  []string
}

func (f *fakeBundles) BlockBundle(_ context.Context, caller auth.Caller, blockKey string) (map[string]any, error) {
	f.calls = append(f.calls, caller.Person+"/"+caller.Athlete+"/"+blockKey)
	return f.bundle, f.err
}

type env struct {
	handler http.Handler
	profile *profile
	bundles *fakeBundles
	objects *store.Memory
}

func newEnv(t *testing.T, profileStatus int) *env {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	e := &env{
		profile: newProfile(t, profileStatus),
		bundles: &fakeBundles{bundle: map[string]any{
			"generatedAt": "2026-01-01T00:00:00Z",
			"block":       map[string]any{"label": "Block One", "blockKey": "block_1", "weekCount": 6.0},
			"historical":  map[string]any{},
			"weekly":      map[string]any{},
		}},
		objects: store.NewMemory(),
	}
	svc, err := service.New(registry, auth.NewAccess(e.profile.URL), e.bundles, e.objects, func() time.Time { return time.Unix(0, 0) })
	if err != nil {
		t.Fatal(err)
	}
	e.handler = Handler(svc, slog.New(slog.NewTextHandler(io.Discard, nil)))
	return e
}

func (e *env) do(method, path string, body string, headers map[string]string) *httptest.ResponseRecorder {
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

const exportBody = `{"pk":"athlete_1","blockKey":"block_1","format":"markdown"}`

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
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, identity)
	if response.Code != http.StatusNotFound || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d body %s", response.Code, e.profile.count(), response.Body)
	}
}

func TestGenerationWithoutJobIs403BeforeEverything(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/nope", `{}`, with(map[string]string{"X-If-Generation-Id": "gen_1"}))
	if response.Code != http.StatusForbidden || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d", response.Code, e.profile.count())
	}
	withTurn := with(map[string]string{"X-If-Generation-Id": "gen_1", "X-If-Turn-Id": "turn_1"})
	if response := e.do("POST", "/operations/analytics.export", exportBody, withTurn); response.Code != http.StatusOK || e.profile.count() != 1 {
		t.Fatalf("status %d hits %d body %s", response.Code, e.profile.count(), response.Body)
	}
}

func TestReservedArgumentsAre403BeforeAccess(t *testing.T) {
	e := newEnv(t, 200)
	for _, key := range []string{"_person_pk", "_access", "_if_job_id"} {
		response := e.do("POST", "/operations/analytics.export", `{"`+key+`":"x"}`, identity)
		if response.Code != http.StatusForbidden {
			t.Fatalf("%s: status %d", key, response.Code)
		}
	}
	if e.profile.count() != 0 {
		t.Fatalf("access called %d times", e.profile.count())
	}
}

func TestMissingPersonIs403WithoutAccessCall(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/analytics.export", exportBody, map[string]string{"X-Athlete-Pk": "athlete_1"})
	if response.Code != http.StatusForbidden || e.profile.count() != 0 {
		t.Fatalf("status %d hits %d", response.Code, e.profile.count())
	}
}

func TestAccessContextReceivesOperationArgumentsAndIdentity(t *testing.T) {
	e := newEnv(t, 200)
	e.do("POST", "/operations/analytics.export", exportBody, identity)
	hit := e.profile.hits[0]
	if hit.headers.Get("X-Person-Pk") != "person_1" || hit.headers.Get("X-Athlete-Pk") != "athlete_1" {
		t.Fatalf("headers %v", hit.headers)
	}
	arguments, _ := hit.body["arguments"].(map[string]any)
	if hit.body["operation"] != "analytics.export" || arguments["blockKey"] != "block_1" {
		t.Fatalf("body %v", hit.body)
	}
}

func TestDeniedAccessIsNeverCached(t *testing.T) {
	e := newEnv(t, 403)
	for range 2 {
		if response := e.do("POST", "/operations/analytics.export", exportBody, identity); response.Code != http.StatusForbidden {
			t.Fatalf("status %d", response.Code)
		}
	}
	if e.profile.count() != 2 || len(e.bundles.calls) != 0 {
		t.Fatalf("hits %d bundle calls %v", e.profile.count(), e.bundles.calls)
	}
	e.profile.status = 500
	if response := e.do("POST", "/operations/analytics.export", exportBody, identity); response.Code != http.StatusInternalServerError {
		t.Fatalf("status %d", response.Code)
	}
}

func TestUnreachableProfileIs503(t *testing.T) {
	e := newEnv(t, 200)
	e.profile.Close()
	if response := e.do("POST", "/operations/analytics.export", exportBody, identity); response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", response.Code)
	}
}

func TestPkConflictIs403AndValidationIs422(t *testing.T) {
	e := newEnv(t, 200)
	if response := e.do("POST", "/operations/analytics.export", `{"pk":"someone_else","blockKey":"b","format":"markdown"}`, identity); response.Code != http.StatusForbidden {
		t.Fatalf("conflict status %d", response.Code)
	}
	if response := e.do("POST", "/operations/analytics.export", `{"blockKey":"b","format":"pdf"}`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("validation status %d", response.Code)
	}
	if response := e.do("POST", "/operations/analytics.export", `[]`, identity); response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("body status %d", response.Code)
	}
}

func TestBlockExportReturnsEnvelope(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("POST", "/operations/analytics.export", `{"blockKey":"block_1","format":"markdown"}`, identity)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
	var result map[string]string
	_ = json.Unmarshal(response.Body.Bytes(), &result)
	content, _ := base64.StdEncoding.DecodeString(result["content_base64"])
	if !strings.HasPrefix(string(content), "# Block One Block Analysis") ||
		result["content_type"] != "text/markdown; charset=utf-8" ||
		result["content_disposition"] != `attachment; filename="block-analysis-block-one.md"` {
		t.Fatalf("result %v", result)
	}
	if e.bundles.calls[0] != "person_1/athlete_1/block_1" {
		t.Fatalf("calls %v", e.bundles.calls)
	}
	xlsx := e.do("POST", "/operations/analytics.export", `{"blockKey":"block_1","format":"xlsx"}`, identity)
	if !strings.Contains(xlsx.Body.String(), "spreadsheetml.sheet") {
		t.Fatalf("xlsx body %s", xlsx.Body)
	}
}

func TestBlockExportCurrentIs400AndMissingIs404(t *testing.T) {
	e := newEnv(t, 200)
	if response := e.do("POST", "/operations/analytics.export", `{"blockKey":"current","format":"xlsx"}`, identity); response.Code != http.StatusBadRequest {
		t.Fatalf("current status %d", response.Code)
	}
	e.bundles.bundle["block"] = map[string]any{"isCurrent": true, "label": "x"}
	if response := e.do("POST", "/operations/analytics.export", exportBody, identity); response.Code != http.StatusBadRequest {
		t.Fatalf("isCurrent status %d", response.Code)
	}
	e.bundles.err = data.ErrNotFound
	if response := e.do("POST", "/operations/analytics.export", exportBody, identity); response.Code != http.StatusNotFound {
		t.Fatalf("missing status %d", response.Code)
	}
}

func TestLifetimeExportReadsLatestOrIs404(t *testing.T) {
	e := newEnv(t, 200)
	body := `{"format":"markdown"}`
	if response := e.do("POST", "/operations/analytics.lifetime_export", body, identity); response.Code != http.StatusNotFound {
		t.Fatalf("missing status %d", response.Code)
	}
	_ = e.objects.Put(context.Background(), "lifetime/athlete_1/latest.md", "text/markdown", []byte("# saved"))
	response := e.do("POST", "/operations/analytics.lifetime_export", body, identity)
	var result map[string]string
	_ = json.Unmarshal(response.Body.Bytes(), &result)
	content, _ := base64.StdEncoding.DecodeString(result["content_base64"])
	if response.Code != http.StatusOK || string(content) != "# saved" || result["content_disposition"] != `attachment; filename="lifetime-report.md"` {
		t.Fatalf("status %d result %v", response.Code, result)
	}
}

func TestJobWrapsResultUnlessNested(t *testing.T) {
	e := newEnv(t, 200)
	_ = e.objects.Put(context.Background(), "lifetime/athlete_1/latest.xlsx", "x", []byte("x"))
	body := `{"format":"xlsx"}`
	wrapped := e.do("POST", "/operations/analytics.lifetime_export", body, with(map[string]string{"X-If-Job-Id": "job_1"}))
	if !strings.Contains(wrapped.Body.String(), `"status":"succeeded"`) {
		t.Fatalf("not wrapped: %s", wrapped.Body)
	}
	nested := e.do("POST", "/operations/analytics.lifetime_export", body, with(map[string]string{"X-If-Job-Id": "job_1", "X-PL-Nested-Operation": "true"}))
	if strings.Contains(nested.Body.String(), `"status":"succeeded"`) {
		t.Fatalf("nested wrapped: %s", nested.Body)
	}
	orphan := e.do("POST", "/operations/analytics.lifetime_export", body, with(map[string]string{"X-PL-Nested-Operation": "true"}))
	if orphan.Code != http.StatusConflict {
		t.Fatalf("orphan nested status %d", orphan.Code)
	}
}

func TestSwaggerDocumentsEveryOperation(t *testing.T) {
	e := newEnv(t, 200)
	registry, _ := contract.Load()
	response := e.do("GET", "/openapi.json", "", nil)
	if response.Code != http.StatusOK {
		t.Fatalf("openapi status %d", response.Code)
	}
	var document map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &document); err != nil {
		t.Fatal(err)
	}
	paths, _ := document["paths"].(map[string]any)
	if len(registry.All()) == 0 {
		t.Fatal("no operations")
	}
	for _, operation := range registry.All() {
		path, _ := paths["/operations/"+operation.Name].(map[string]any)
		post, _ := path["post"].(map[string]any)
		if post == nil {
			t.Fatalf("operation %s undocumented", operation.Name)
		}
		names := map[string]bool{}
		for _, raw := range post["parameters"].([]any) {
			parameter := raw.(map[string]any)
			if parameter["in"] == "header" {
				names[parameter["name"].(string)] = true
			}
		}
		if !names["X-Person-Pk"] || !names["X-Athlete-Pk"] {
			t.Fatalf("%s lacks identity header parameters: %v", operation.Name, names)
		}
		request, _ := post["requestBody"].(map[string]any)
		content, _ := request["content"].(map[string]any)
		media, _ := content["application/json"].(map[string]any)
		schema, _ := media["schema"].(map[string]any)
		if schema["properties"] == nil {
			t.Fatalf("%s request schema missing: %v", operation.Name, request)
		}
	}
	for _, path := range []string{"/health", "/mcp"} {
		if paths[path] == nil {
			t.Fatalf("%s undocumented", path)
		}
	}
	if docs := e.do("GET", "/docs", "", nil); docs.Code != http.StatusOK || !strings.Contains(strings.ToLower(docs.Body.String()), "swagger") {
		t.Fatalf("docs status %d", docs.Code)
	}
}

func TestHealth(t *testing.T) {
	e := newEnv(t, 200)
	response := e.do("GET", "/health", "", nil)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"status":"ok"`) {
		t.Fatalf("status %d body %s", response.Code, response.Body)
	}
}

func rpc(t *testing.T, e *env, body string) (int, map[string]any) {
	t.Helper()
	response := e.do("POST", "/mcp", body, identity)
	var decoded map[string]any
	_ = json.Unmarshal(response.Body.Bytes(), &decoded)
	return response.Code, decoded
}

func TestMCPToolsListAndCall(t *testing.T) {
	e := newEnv(t, 200)
	if code, _ := rpc(t, e, `{"jsonrpc":"2.0","method":"notifications/initialized"}`); code != http.StatusAccepted {
		t.Fatalf("notification status %d", code)
	}
	_, initialized := rpc(t, e, `{"jsonrpc":"2.0","id":1,"method":"initialize"}`)
	if initialized["result"].(map[string]any)["protocolVersion"] != "2025-03-26" {
		t.Fatalf("initialize %v", initialized)
	}
	_, listed := rpc(t, e, `{"jsonrpc":"2.0","id":2,"method":"tools/list"}`)
	tools := listed["result"].(map[string]any)["tools"].([]any)
	if len(tools) != 2 || tools[0].(map[string]any)["outputSchema"] == nil {
		t.Fatalf("tools %v", tools)
	}
	_, unknown := rpc(t, e, `{"jsonrpc":"2.0","id":3,"method":"nope"}`)
	if unknown["error"].(map[string]any)["code"] != -32601.0 {
		t.Fatalf("unknown %v", unknown)
	}
	_, called := rpc(t, e, `{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"analytics.export","arguments":{"blockKey":"block_1","format":"markdown"}}}`)
	result := called["result"].(map[string]any)
	if result["isError"] != false || result["structuredContent"] == nil {
		t.Fatalf("call %v", result)
	}
	_, failed := rpc(t, e, `{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"nope"}}`)
	if failed["result"].(map[string]any)["isError"] != true {
		t.Fatalf("failed %v", failed)
	}
}
