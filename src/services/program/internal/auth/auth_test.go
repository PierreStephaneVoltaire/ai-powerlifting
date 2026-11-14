package auth

import (
	"net/http"
	"testing"

	"powerlifting/program/internal/contract"
)

func TestBackendRecognisedByServiceAccount(t *testing.T) {
	yes := []string{"spiffe://cluster.local/ns/pl/sa/powerlifting-app-backend", "cluster.local/ns/pl/sa/powerlifting-app-backend"}
	no := []string{"cluster.local/ns/pl/sa/pl-analytics-ai", "cluster.local/ns/pl/sa/x-powerlifting-app-backend2", ""}
	for _, source := range yes {
		if !(Caller{Source: source}).IsBackend() {
			t.Errorf("%q should be backend", source)
		}
	}
	for _, source := range no {
		if (Caller{Source: source}).IsBackend() {
			t.Errorf("%q should not be backend", source)
		}
	}
}

func TestFromHeadersReadsExecutionContext(t *testing.T) {
	headers := http.Header{}
	headers.Set("X-Person-Pk", "p")
	headers.Set("X-If-Turn-Id", "turn_1")
	headers.Set("X-If-Job-Id", "job_1")
	headers.Set("X-If-Generation-Id", "gen_1")
	headers.Set("X-If-Generation-Attempt", "3")
	headers.Set("X-PL-Nested-Operation", "true")
	caller := FromHeaders(headers)
	if caller.ActiveJob() != "turn_1" || !caller.Nested || caller.Generation == nil || caller.Generation.Attempt != 3 {
		t.Fatalf("caller %+v", caller)
	}
}

func TestScopeForcesAthleteAndRejectsConflicts(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	operation, _ := registry.Get("program_get")
	caller := Caller{Person: "p", Athlete: "a1"}
	scoped, err := Scope(operation, map[string]any{"block": "all"}, caller, map[string]any{})
	if err != nil || scoped["pk"] != "a1" {
		t.Fatalf("scoped %v err %v", scoped, err)
	}
	if _, err := Scope(operation, map[string]any{"pk": "other"}, caller, nil); err == nil {
		t.Fatal("conflicting pk accepted")
	}
	if _, err := Scope(operation, map[string]any{}, Caller{Person: "p"}, nil); err == nil {
		t.Fatal("missing athlete accepted")
	}
}

func TestEveryProgramOperationHasPkInSchema(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	for _, operation := range registry.All() {
		if !operation.HasInput("pk") {
			t.Errorf("%s: pk missing from input schema", operation.Name)
		}
	}
}
