package service

import (
	"net/http"
	"strings"
	"testing"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/contract"
)

func detail(t *testing.T, err error) string {
	t.Helper()
	failure, ok := err.(*apperr.Error)
	if !ok {
		t.Fatalf("expected apperr, got %v", err)
	}
	text, _ := failure.MarshalJSON()
	return string(text)
}

func TestInboundChecksRunInTheSpecifiedOrder(t *testing.T) {
	h := newHarness(t)
	args := func(extra map[string]any) map[string]any {
		out := map[string]any{"pk": "athlete_1", "block_key": "block_1"}
		for key, value := range extra {
			out[key] = value
		}
		return out
	}
	generation := person()
	generation.Generation = &auth.Generation{ID: "g", Attempt: 1}
	noPerson := auth.Caller{Athlete: "athlete_1"}
	nested := person()
	nested.Nested = true

	cases := []struct {
		name      string
		operation string
		arguments map[string]any
		caller    auth.Caller
		status    int
		contains  string
		accessed  bool
	}{
		{"generation without a turn wins over an unknown operation", "nope", args(nil), generation, 403, "Generation requires an active native turn", false},
		{"unknown operation before reserved fields", "nope", args(map[string]any{"_access": 1}), person(), 404, "Unknown operation", false},
		{"reserved fields before access evaluation", "block_correlation_analysis", args(map[string]any{"_person_pk": "x"}), noPerson, 403, "Reserved authorization fields", false},
		{"athlete scope conflict after access evaluation", "block_correlation_analysis", args(map[string]any{"pk": "someone_else"}), person(), 403, "ownership conflicts", true},
		{"validation after scoping", "block_correlation_analysis", args(map[string]any{"block_key": 7}), person(), 422, "validation", true},
		{"nested call without an execution", "block_correlation_analysis", args(nil), nested, 409, "Nested operation requires an active domain execution", true},
		{"nested AI call without an active execution", "block_correlation_analysis", args(nil), func() auth.Caller { c := inCoachJob(person(), "", 0); c.Nested = true; return c }(), 409, "Active domain execution unavailable", true},
	}
	for _, tc := range cases {
		before := len(h.access.calls)
		_, err := h.call(t, tc.operation, tc.arguments, tc.caller)
		if err == nil {
			t.Errorf("%s: expected an error", tc.name)
			continue
		}
		if status := statusOf(t, err); status != tc.status || !strings.Contains(detail(t, err), tc.contains) {
			t.Errorf("%s: got %d %s", tc.name, status, detail(t, err))
		}
		if accessed := len(h.access.calls) > before; accessed != tc.accessed {
			t.Errorf("%s: access evaluation = %v, want %v", tc.name, accessed, tc.accessed)
		}
	}
	if h.coach.count() != 0 {
		t.Fatal("rejected requests must never reach the coach")
	}
}

func TestAccessFailuresPropagateTheirStatus(t *testing.T) {
	h := newHarness(t)
	h.access.deny = http.StatusForbidden
	if _, err := h.call(t, "block_correlation_analysis", map[string]any{"pk": "athlete_1", "block_key": "b"}, person()); statusOf(t, err) != http.StatusForbidden {
		t.Fatalf("got %v", err)
	}
}

func TestInternalOnlyOperationsNeedTheBackendAccount(t *testing.T) {
	operations := `[{"name":"secret","domain":"analytics-ai","description":"d","execution":"deterministic","ownership":"athlete","input_schema":{"type":"object","required":["x"],"properties":{"x":{"type":"string"}}},"result_schema":{"type":"object"}}]`
	registry, err := contract.Parse([]byte(operations), []byte(`{"secret":{"internal_only":true}}`))
	if err != nil {
		t.Fatal(err)
	}
	h := newHarness(t)
	h.svc.Registry = registry
	if _, err := h.call(t, "secret", map[string]any{"x": "1"}, auth.Caller{Person: "p", Athlete: "a", Source: "cluster.local/ns/pl/sa/pl-analytics"}); statusOf(t, err) != http.StatusForbidden || !strings.Contains(err.Error(), "internal to the gateway") {
		t.Fatalf("got %v", err)
	}
	if len(h.access.calls) != 1 {
		t.Fatal("access evaluation precedes the internal-only check")
	}
	if _, err := h.call(t, "secret", map[string]any{}, person()); statusOf(t, err) != http.StatusUnprocessableEntity {
		t.Fatalf("the backend passes the check and reaches validation: %v", err)
	}
}
