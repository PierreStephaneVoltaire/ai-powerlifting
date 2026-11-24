package serve

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/auth"
	"powerlifting/liftprofiles/internal/contract"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/service"
)

type testAccess struct{}

func (testAccess) Fetch(_ context.Context, _ string, _ map[string]any, c auth.Caller) error {
	if c.Person == "" || c.Athlete == "" {
		return apperr.Forbidden("missing scope")
	}
	return nil
}

func TestHTTPRejectsSpoofedAndMissingIdentity(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc := &service.Service{Registry: registry, Access: testAccess{}, Handlers: map[string]func(context.Context, map[string]any, execution.Inferer) (any, error){"program_update_lift_profiles": func(_ context.Context, args map[string]any, _ execution.Inferer) (any, error) {
		return map[string]any{"success": true}, nil
	}}}
	handler := New(&API{Service: svc, Domain: contract.Domain})
	for _, test := range []struct {
		body   string
		person string
		status int
	}{
		{`{"lift_profiles":[],"_person_pk":"forged"}`, "person", http.StatusForbidden},
		{`{"lift_profiles":[]}`, "", http.StatusForbidden},
		{`{"lift_profiles":[],"pk":"another"}`, "person", http.StatusForbidden},
		{`{"lift_profiles":[]}`, "person", http.StatusOK},
	} {
		req := httptest.NewRequest(http.MethodPost, "/operations/program_update_lift_profiles", strings.NewReader(test.body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Person-Pk", test.person)
		req.Header.Set("X-Athlete-Pk", "athlete")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != test.status {
			t.Errorf("body %s: got %d %s", test.body, rec.Code, rec.Body.String())
		}
	}
}
