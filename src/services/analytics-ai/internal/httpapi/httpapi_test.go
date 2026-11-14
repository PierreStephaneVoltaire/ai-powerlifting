package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"

	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/coach"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
	"powerlifting/analytics-ai/internal/service"
)

type access struct {
	mu      sync.Mutex
	callers []auth.Caller
}

func (a *access) Fetch(_ context.Context, _ string, _ map[string]any, caller auth.Caller) (auth.Access, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.callers = append(a.callers, caller)
	return auth.Access{"settings_pk": caller.Person, "is_self": true, "permissions": []any{"analytics:read"}}, nil
}

type jobs struct{ submitted int }

func (j *jobs) Submit(context.Context, coach.Submission) (coach.Job, error) {
	j.submitted++
	return coach.Job{ID: "job_1", Status: "running"}, nil
}

func (j *jobs) Status(context.Context, string, string, string) (coach.Job, error) {
	return coach.Job{ID: "job_1", Status: "running"}, nil
}

func newServer(t *testing.T) (*httptest.Server, *access, *jobs) {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	redisServer := miniredis.RunT(t)
	kv := cache.Redis{Client: redis.NewClient(&redis.Options{Addr: redisServer.Addr()})}
	a, j := &access{}, &jobs{}
	svc := &service.Service{Registry: registry, Access: a, Coach: j, KV: kv, Backend: generation.NewMemory(), Executions: execution.New(cache.Prompts{KV: kv}), Now: time.Now}
	server := httptest.NewServer(New(&API{Service: svc, Domain: contract.Domain}))
	t.Cleanup(server.Close)
	return server, a, j
}

func do(t *testing.T, method, url, body string, headers map[string]string) (int, map[string]any, string) {
	t.Helper()
	request, _ := http.NewRequest(method, url, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for name, value := range headers {
		request.Header.Set(name, value)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	raw, _ := io.ReadAll(response.Body)
	var parsed map[string]any
	_ = json.Unmarshal(raw, &parsed)
	return response.StatusCode, parsed, string(raw)
}

var identity = map[string]string{"X-Person-Pk": "person_1", "X-Athlete-Pk": "athlete_1"}

func TestSwaggerDocumentsEveryOperationWithHeaders(t *testing.T) {
	server, _, _ := newServer(t)
	status, document, _ := do(t, http.MethodGet, server.URL+"/openapi.json", "", nil)
	if status != http.StatusOK {
		t.Fatalf("openapi.json: %d", status)
	}
	registry, _ := contract.Load()
	paths := document["paths"].(map[string]any)
	wantHeaders := []string{"X-Person-Pk", "X-Athlete-Pk", "X-PL-Source-Principal", "X-IF-Job-Id", "X-IF-Turn-Id", "X-PL-Nested-Operation", "X-IF-Generation-Id", "X-IF-Generation-Attempt"}
	check := func(path, method string, headers bool) map[string]any {
		item, ok := paths[path].(map[string]any)
		if !ok {
			t.Errorf("%s is not documented", path)
			return nil
		}
		operation, ok := item[method].(map[string]any)
		if !ok {
			t.Errorf("%s %s is not documented", method, path)
			return nil
		}
		if headers {
			documented := map[string]bool{}
			for _, parameter := range operation["parameters"].([]any) {
				entry := parameter.(map[string]any)
				if entry["in"] == "header" {
					documented[entry["name"].(string)] = true
				}
			}
			for _, name := range wantHeaders {
				if !documented[name] {
					t.Errorf("%s %s lacks header parameter %s", method, path, name)
				}
			}
		}
		return operation
	}
	if len(registry.All()) != 8 {
		t.Fatalf("expected the eight analytics-ai operations, got %d", len(registry.All()))
	}
	for _, operation := range registry.All() {
		documented := check("/operations/"+operation.Name, "post", true)
		if documented == nil {
			continue
		}
		body := documented["requestBody"].(map[string]any)["content"].(map[string]any)["application/json"].(map[string]any)["schema"].(map[string]any)
		properties, _ := body["properties"].(map[string]any)
		for name := range operation.InputSchema["properties"].(map[string]any) {
			if _, present := properties[name]; !present {
				t.Errorf("%s: request schema lacks %s", operation.Name, name)
			}
		}
		responses := documented["responses"].(map[string]any)
		for _, code := range []string{"200", "202"} {
			if _, present := responses[code]; !present {
				t.Errorf("%s: response %s undocumented", operation.Name, code)
			}
		}
	}
	check("/executions/{execution_id}", "post", true)
	check("/generations/{generation_id}", "get", true)
	check("/mcp", "post", true)
	check("/health", "get", false)

	_, _, page := do(t, http.MethodGet, server.URL+"/docs", "", nil)
	if !strings.Contains(strings.ToLower(page), "swagger") || !strings.Contains(page, "/openapi") {
		t.Fatal("/docs must serve Swagger UI for the generated document")
	}
}

func TestHealth(t *testing.T) {
	server, _, _ := newServer(t)
	status, body, _ := do(t, http.MethodGet, server.URL+"/health", "", nil)
	if status != http.StatusOK || body["status"] != "ok" || body["domain"] != "analytics-ai" {
		t.Fatalf("got %d %v", status, body)
	}
}

func TestOperationSubmitsThroughHTTPWithForwardedIdentity(t *testing.T) {
	server, access, jobs := newServer(t)
	headers := map[string]string{"X-PL-Source-Principal": "cluster.local/ns/pl/sa/powerlifting-app-backend"}
	for name, value := range identity {
		headers[name] = value
	}
	status, body, _ := do(t, http.MethodPost, server.URL+"/operations/block_correlation_analysis", `{"block_key": "block_1"}`, headers)
	if status != http.StatusAccepted || body["job_id"] != "job_1" || body["generation_id"] == nil || jobs.submitted != 1 {
		t.Fatalf("got %d %v", status, body)
	}
	if caller := access.callers[0]; caller.Person != "person_1" || caller.Athlete != "athlete_1" || !caller.IsBackend() {
		t.Fatalf("headers must reach the pipeline: %+v", caller)
	}
	status, body, _ = do(t, http.MethodGet, server.URL+"/generations/"+body["generation_id"].(string), "", identity)
	if status != http.StatusOK || body["status"] != "starting" {
		t.Fatalf("generation status: %d %v", status, body)
	}
}

func TestErrorShapesMatchTheFastAPIContract(t *testing.T) {
	server, _, _ := newServer(t)
	cases := []struct {
		name, method, path, body string
		headers                  map[string]string
		status                   int
		contains                 string
	}{
		{"unknown operation", http.MethodPost, "/operations/nope", `{}`, identity, 404, `{"detail":"Unknown operation"}`},
		{"body must be an object", http.MethodPost, "/operations/block_correlation_analysis", `[1]`, identity, 422, `"dict_type"`},
		{"generation without a turn", http.MethodPost, "/operations/block_correlation_analysis", `{}`, map[string]string{"X-IF-Generation-Id": "g"}, 403, `Generation requires an active native turn`},
		{"unknown generation", http.MethodGet, "/generations/missing", ``, identity, 404, `"code":"not_found"`},
		{"athlete required for generations", http.MethodGet, "/generations/missing", ``, map[string]string{"X-Person-Pk": "p"}, 403, `Authenticated Athlete required`},
		{"unknown execution", http.MethodPost, "/executions/missing", `{}`, identity, 409, `"code":"uncertain"`},
	}
	for _, tc := range cases {
		status, _, raw := do(t, tc.method, server.URL+tc.path, tc.body, tc.headers)
		if status != tc.status || !strings.Contains(strings.ReplaceAll(raw, " ", ""), strings.ReplaceAll(tc.contains, " ", "")) {
			t.Errorf("%s: got %d %s", tc.name, status, raw)
		}
	}
}

func rpc(t *testing.T, server *httptest.Server, request string) (int, map[string]any) {
	t.Helper()
	status, body, _ := do(t, http.MethodPost, server.URL+"/mcp", request, identity)
	return status, body
}

func TestMCP(t *testing.T) {
	server, _, _ := newServer(t)
	_, initialized := rpc(t, server, `{"jsonrpc":"2.0","id":1,"method":"initialize"}`)
	info := initialized["result"].(map[string]any)["serverInfo"].(map[string]any)
	if info["name"] != "powerlifting-analytics-ai" {
		t.Fatalf("got %v", initialized)
	}
	_, listed := rpc(t, server, `{"jsonrpc":"2.0","id":2,"method":"tools/list"}`)
	tools := listed["result"].(map[string]any)["tools"].([]any)
	if len(tools) != 8 {
		t.Fatalf("expected a tool per operation, got %d", len(tools))
	}
	for _, entry := range tools {
		tool := entry.(map[string]any)
		if tool["name"] == "correlation_analysis" && tool["outputSchema"].(map[string]any)["required"] == nil {
			t.Fatal("AI tools advertise the job output schema")
		}
	}
	status, _ := rpc(t, server, `{"jsonrpc":"2.0","method":"notifications/initialized"}`)
	if status != http.StatusAccepted {
		t.Fatalf("notifications are acknowledged with 202, got %d", status)
	}
	_, unknown := rpc(t, server, `{"jsonrpc":"2.0","id":3,"method":"nope"}`)
	if unknown["error"].(map[string]any)["code"] != float64(-32601) {
		t.Fatalf("got %v", unknown)
	}
	_, called := rpc(t, server, `{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"block_correlation_analysis","arguments":{"block_key":"b"}}}`)
	result := called["result"].(map[string]any)
	if result["isError"] != false || result["structuredContent"].(map[string]any)["generation_id"] == nil {
		t.Fatalf("got %v", called)
	}
	_, failed := rpc(t, server, `{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"missing","arguments":{}}}`)
	if failed["result"].(map[string]any)["isError"] != true {
		t.Fatalf("got %v", failed)
	}
}
