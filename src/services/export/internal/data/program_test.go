package data

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"powerlifting/export/internal/auth"
)

func TestProgramGetForwardsIdentityAndOnlySelection(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/operations/program_get" || r.Header.Get("X-Person-Pk") != "person" || r.Header.Get("X-Athlete-Pk") != "athlete" {
			t.Error("missing scope or incorrect operation")
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["pk"] != "athlete" || body["block"] != "past" || body["_access"] != nil {
			t.Errorf("unexpected arguments %#v", body)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"meta":{"program_name":"Test"}}`))
	}))
	defer server.Close()
	program, err := NewProgramClient(server.URL).Get(context.Background(), auth.Caller{Person: "person", Athlete: "athlete"}, map[string]any{"block": "past", "_access": "forged"})
	if err != nil || program["meta"] == nil {
		t.Fatalf("got %v, %v", program, err)
	}
}
