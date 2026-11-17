package httpapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"powerlifting/assistant/internal/access"
)

func TestTurnRequiresAIEntitlement(t *testing.T) {
	profile := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"permissions":["sessions:read"]}`))
	}))
	defer profile.Close()
	server := &Server{Access: access.New(profile.URL), AllowedCallers: []string{"backend"}}
	req := httptest.NewRequest("POST", "/v1/conversations/powerlifting:athlete:web:person:general/turns", strings.NewReader(`{"messages":[{"role":"user","content":"hello"}]}`))
	req.Header.Set("X-PL-Source-Principal", "spiffe://cluster.local/ns/powerlifting/sa/backend")
	req.Header.Set("X-Person-Pk", "person")
	req.Header.Set("X-Athlete-Pk", "athlete")
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, req)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}
