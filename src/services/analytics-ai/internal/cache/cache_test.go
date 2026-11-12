package cache

import (
	"context"
	"encoding/json"
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

func TestKeyLayout(t *testing.T) {
	if got := Key("athlete_1", "block_correlation_analysis", "abc"); got != "pl:ai-cache:exact:athlete_1:block_correlation_analysis:abc" {
		t.Fatal(got)
	}
}

func TestPromptRoundTripUsesTTLAndKey(t *testing.T) {
	server := miniredis.RunT(t)
	kv := Redis{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	prompts := Prompts{KV: kv}
	ctx := context.Background()
	request := Request{Messages: []any{map[string]any{"role": "user", "content": "hi"}}, Tools: []any{}}
	if _, hit := prompts.Exact(ctx, "athlete_1", "op", request); hit {
		t.Fatal("unexpected hit")
	}
	prompts.Remember(ctx, "athlete_1", "op", request, map[string]any{"choices": []any{}})
	if _, hit := prompts.Exact(ctx, "athlete_1", "op", request); !hit {
		t.Fatal("expected hit")
	}
	hash, _ := request.Hash()
	key := Key("athlete_1", "op", hash)
	if !server.Exists(key) || server.TTL(key) != 30*24*time.Hour {
		t.Fatalf("key %s ttl %v", key, server.TTL(key))
	}
	if _, hit := prompts.Exact(ctx, "athlete_2", "op", request); hit {
		t.Fatal("cache must be athlete scoped")
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
