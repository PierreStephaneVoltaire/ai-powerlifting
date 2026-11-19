package llm

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPrivateEmbeddingBatch(t *testing.T) {
	for _, tc := range []struct {
		name, response string
		fail           bool
	}{
		{"reordered", `{"data":[{"index":1,"embedding":[2]},{"index":0,"embedding":[1]}]}`, false},
		{"missing", `{"data":[{"index":0,"embedding":[1]}]}`, true},
		{"duplicate", `{"data":[{"index":0,"embedding":[1]},{"index":0,"embedding":[2]}]}`, true},
		{"missing index", `{"data":[{"embedding":[1]},{"index":1,"embedding":[2]}]}`, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var body map[string]any
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				inputs, ok := body["input"].([]any)
				if !ok || len(inputs) != 2 || inputs[0] != "first" || inputs[1] != "second" {
					t.Errorf("bad inputs: %v", body["input"])
				}
				if r.Header.Get("Cache-Control") != "no-store" || body["no-log"] != true || body["cache"].(map[string]any)["no-store"] != true {
					t.Error("private controls missing")
				}
				fmt.Fprint(w, tc.response)
			}))
			defer server.Close()
			vectors, err := New(server.URL, "test").EmbedPrivateBatch(context.Background(), "model", []string{"first", "second"})
			if (err != nil) != tc.fail {
				t.Fatalf("vectors %v error %v", vectors, err)
			}
			if !tc.fail && (vectors[0][0] != 1 || vectors[1][0] != 2) {
				t.Fatalf("wrong ordering: %v", vectors)
			}
		})
	}
}
