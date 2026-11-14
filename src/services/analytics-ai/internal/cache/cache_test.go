package cache

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"

	"powerlifting/analytics-ai/internal/pyjson"
)

func requestFrom(t *testing.T, text string) Request {
	t.Helper()
	value, err := pyjson.Decode([]byte(text))
	if err != nil {
		t.Fatal(err)
	}
	object := value.(map[string]any)
	request := Request{ResponseFormat: object["response_format"]}
	request.Messages, _ = object["messages"].([]any)
	request.Tools, _ = object["tools"].([]any)
	if request.Messages == nil && object["messages"] != nil {
		request.Messages = []any{}
	}
	return request
}

func TestRequestHashMatchesPython(t *testing.T) {
	raw, err := os.ReadFile("../generation/testdata/vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var data struct {
		Requests []struct {
			Request string `json:"request"`
			Hash    string `json:"hash"`
		} `json:"requests"`
	}
	if err := json.Unmarshal(raw, &data); err != nil {
		t.Fatal(err)
	}
	if len(data.Requests) == 0 {
		t.Fatal("no vectors")
	}
	for index, vector := range data.Requests {
		got, err := requestFrom(t, vector.Request).Hash()
		if err != nil || got != vector.Hash {
			t.Errorf("vector %d: got %s (%v) want %s", index, got, err, vector.Hash)
		}
	}
}

func TestPromptsLookupAndRememberUseCacheService(t *testing.T) {
	server := miniredis.RunT(t)
	_ = server.Set("pl:analysis-version:athlete_1", "4")
	kv := Redis{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	bodies := map[string]promptBody{}
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body promptBody
		_ = json.NewDecoder(r.Body).Decode(&body)
		bodies[r.URL.Path] = body
		if r.URL.Path == "/lookup" {
			_, _ = w.Write([]byte(`{"hit":true,"layer":"semantic","response":{"choices":[]}}`))
			return
		}
		_, _ = w.Write([]byte(`{"entry_id":"e"}`))
	}))
	defer service.Close()
	prompts := Prompts{KV: kv, URL: service.URL, Now: func() time.Time { return time.Date(2026, 11, 14, 0, 0, 0, 0, time.UTC) }}
	ctx := context.Background()
	request := Request{Messages: []any{map[string]any{"role": "user", "content": "hi"}}, Tools: []any{}}
	response, layer, hit := prompts.Lookup(ctx, "athlete_1", "op", request)
	if !hit || layer != "semantic" || response["choices"] == nil {
		t.Fatalf("lookup %v %s %v", response, layer, hit)
	}
	prompts.Remember(ctx, "athlete_1", "op", request, map[string]any{"choices": []any{}})
	for _, path := range []string{"/lookup", "/store"} {
		body := bodies[path]
		if body.Athlete != "athlete_1" || body.Operation != "op" || body.Context != (promptContext{Date: "2026-11-14", AnalysisVersion: "4"}) {
			t.Fatalf("%s body %+v", path, body)
		}
	}
}

func TestPromptsServiceFailureIsMiss(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusInternalServerError) }))
	defer service.Close()
	server := miniredis.RunT(t)
	prompts := Prompts{KV: Redis{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}, URL: service.URL}
	if _, _, hit := prompts.Lookup(context.Background(), "a", "op", Request{}); hit {
		t.Fatal("unexpected hit")
	}
}

func TestAnalysisVersionDefaultsToZero(t *testing.T) {
	server := miniredis.RunT(t)
	kv := Redis{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	ctx := context.Background()
	if got := AnalysisVersion(ctx, kv, "a"); got != "0" {
		t.Fatal(got)
	}
	_ = server.Set("pl:analysis-version:a", "12")
	if got := AnalysisVersion(ctx, kv, "a"); got != "12" {
		t.Fatal(got)
	}
}
