package serve

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"

	"powerlifting/glossary/internal/athlete"
	"powerlifting/glossary/internal/auth"
	"powerlifting/glossary/internal/cache"
	"powerlifting/glossary/internal/coach"
	"powerlifting/glossary/internal/contract"
	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/generic"
	"powerlifting/glossary/internal/service"
	"powerlifting/glossary/internal/store"
)

type allow struct{}

func (allow) Fetch(context.Context, string, map[string]any, auth.Caller) error { return nil }

type queue struct{}

func (queue) Submit(context.Context, coach.Submission) (coach.Job, error) {
	return coach.Job{ID: "job_9", Status: "running"}, nil
}

type noProgram struct{}

func (noProgram) Program(context.Context, string) (athlete.Program, error) {
	return athlete.Program{}, nil
}

func (noProgram) Instances(context.Context, string, athlete.Program, string) ([]map[string]any, error) {
	return nil, nil
}

func newServer(t *testing.T) *httptest.Server {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	valkey := cache.Valkey{Client: redis.NewClient(&redis.Options{Addr: miniredis.RunT(t).Addr()})}
	memory := store.NewMemory()
	svc, err := service.New(&service.Service{
		Registry: registry, Access: allow{}, Store: memory, Athletes: noProgram{}, Coach: queue{}, Executions: execution.New(cache.Prompts{Valkey: valkey, Now: time.Now}),
		Generic: &generic.Estimator{Store: memory, Coach: queue{}, Interval: time.Minute, Now: time.Now}, Cache: valkey, Now: time.Now,
	})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(New(&API{Service: svc, Domain: contract.Domain}))
	t.Cleanup(server.Close)
	return server
}

func post(t *testing.T, url, body string, headers map[string]string) (int, map[string]any) {
	t.Helper()
	request, _ := http.NewRequest(http.MethodPost, url, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	raw, _ := io.ReadAll(response.Body)
	var decoded map[string]any
	_ = json.Unmarshal(raw, &decoded)
	return response.StatusCode, decoded
}

var athleteHeaders = map[string]string{"X-Person-Pk": "p1", "X-Athlete-Pk": "a1"}

func TestOperationRoundTrip(t *testing.T) {
	server := newServer(t)
	status, body := post(t, server.URL+"/operations/exercise_upsert", `{"exercise":{"id":"x1","name":"Row"}}`, athleteHeaders)
	if status != 200 || body["id"] != "x1" {
		t.Fatalf("upsert %d %v", status, body)
	}
	status, body = post(t, server.URL+"/operations/exercise_get_glossary", `{}`, athleteHeaders)
	if status != 200 || len(body["exercises"].([]any)) != 1 || body["pk"] != "a1" {
		t.Fatalf("glossary %d %v", status, body)
	}
}

func TestRejectionsUseDetailEnvelope(t *testing.T) {
	server := newServer(t)
	if status, body := post(t, server.URL+"/operations/nope", `{}`, athleteHeaders); status != 404 || body["detail"] != "Unknown operation" {
		t.Fatalf("unknown %d %v", status, body)
	}
	if status, _ := post(t, server.URL+"/operations/exercise_get_glossary", `[]`, athleteHeaders); status != 422 {
		t.Fatalf("array body %d", status)
	}
	if status, _ := post(t, server.URL+"/operations/exercise_get_glossary", `{}`, map[string]string{"X-Person-Pk": "p1"}); status != 403 {
		t.Fatalf("no athlete %d", status)
	}
	if status, _ := post(t, server.URL+"/operations/exercise_upsert", `{"exercise":{}}`, athleteHeaders); status != 422 {
		t.Fatalf("schema violation %d", status)
	}
}

func TestAIOperationWithoutJobIsAccepted(t *testing.T) {
	server := newServer(t)
	status, body := post(t, server.URL+"/operations/glossary_estimate_batch", `{"ids":["sq"],"aspects":["fatigue"]}`, athleteHeaders)
	if status != 202 || body["job_id"] != "job_9" {
		t.Fatalf("submit %d %v", status, body)
	}
}

func TestMCPListsOperationsAndCallsTools(t *testing.T) {
	server := newServer(t)
	_, listed := post(t, server.URL+"/mcp", `{"jsonrpc":"2.0","id":1,"method":"tools/list"}`, athleteHeaders)
	tools := listed["result"].(map[string]any)["tools"].([]any)
	names := map[string]bool{}
	for _, tool := range tools {
		names[tool.(map[string]any)["name"].(string)] = true
	}
	if len(names) != 8 || !names["glossary_generic_estimate"] || names["exercise_search"] {
		t.Fatalf("tools %v", names)
	}
	_, called := post(t, server.URL+"/mcp", `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"exercise_get_glossary","arguments":{}}}`, athleteHeaders)
	if result := called["result"].(map[string]any); result["isError"] != false || result["structuredContent"].(map[string]any)["pk"] != "a1" {
		t.Fatalf("call %v", called)
	}
}

func TestHealthAndDocs(t *testing.T) {
	server := newServer(t)
	for _, path := range []string{"/health", "/healthz", "/docs", "/openapi.json"} {
		response, err := http.Get(server.URL + path)
		if err != nil || response.StatusCode != 200 {
			t.Fatalf("%s: %v %v", path, err, response)
		}
		response.Body.Close()
	}
}
