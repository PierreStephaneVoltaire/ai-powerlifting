package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPrivateRequestsDisableCachingAndLogging(t *testing.T) {
	count := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count++
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
			return
		}
		cache, ok := body["cache"].(map[string]any)
		if !ok || cache["no-store"] != true || cache["no-cache"] != true || body["no-log"] != true {
			t.Errorf("private controls absent: %v", body)
		}
		if r.URL.Path == "/v1/chat/completions" {
			if body["store"] != false {
				t.Errorf("store is not false")
			}
			w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
		} else {
			w.Write([]byte(`{"data":[{"embedding":[1]}]}`))
		}
	}))
	defer server.Close()
	client := New(server.URL, "key")
	if _, err := client.Chat(context.Background(), ChatRequest{Model: "reader", Private: true, Messages: []Message{{Role: "user", Content: "secret"}}}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.EmbedPrivate(context.Background(), "embed", "secret"); err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Fatalf("calls: %d", count)
	}
}
