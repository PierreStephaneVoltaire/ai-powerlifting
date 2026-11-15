package service

import (
	"strings"
	"testing"
	"time"

	"powerlifting/glossary/internal/auth"
)

func pendingCatalog(h *harness, t *testing.T, extra map[string]any) {
	t.Helper()
	item := map[string]any{"generic_status": "pending", "generic_pending": "1", "generic_attempts": 0.0, "created_by": "a1", "created_by_person": "p1", "description": "Sets up", "primary_muscles": []any{}}
	for key, value := range extra {
		item[key] = value
	}
	h.seedCatalog(t, "g1", "Odd Lift", item)
}

var genericAnswer = element("g1", map[string]any{
	"muscles":       map[string]any{"primary_muscles": []any{"lats"}, "secondary_muscles": []any{"biceps"}, "tertiary_muscles": []any{}, "reasoning": "pull"},
	"text":          map[string]any{"description": "Ignored", "how_to_perform": "1. Pull", "why_do_it": "Back"},
	"lift_transfer": map[string]any{"squat": 0.0, "bench": 0.0, "deadlift": 0.1, "reasoning": "low"},
	"fatigue":       map[string]any{"axial": 0.2, "neural": 0.3, "peripheral": 0.4, "systemic": 0.1, "reasoning": "light"},
})

func TestGenericEstimateFillsCatalogFromDefinitionOnlyInOneCall(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.seedCatalog(t, "g2", "Other Lift", map[string]any{"generic_status": "pending", "generic_pending": "1", "generic_attempts": 0.0, "primary_muscles": []any{"quads"}, "description": "d", "how_to_perform": "h", "why_do_it": "w", "lift_transfer": map[string]any{"squat": 0.5, "bench": 0.0, "deadlift": 0.0, "source": "user", "reasoning": "mine"}})
	h.redis.Set("pl:analysis-version:a1", "5")
	h.redis.Set("pl:analysis-version:a2", "8")
	h.redis.Set("pl:analysis:a2:section", "{}")
	creator := auth.Caller{Person: "p1", Athlete: "a1"}
	other := element("g2", map[string]any{"fatigue": map[string]any{"axial": 0.1, "neural": 0.1, "peripheral": 0.1, "systemic": 0.1, "reasoning": "x"}})
	result, asked := h.drive(t, "glossary_generic_estimate", map[string]any{"ids": []any{"g1", "g2", "missing"}}, creator, answer(genericAnswer, other))
	if len(asked) != 1 || len(result["saved"].([]any)) != 2 {
		t.Fatalf("result %v asked %d", result, len(asked))
	}
	failed := result["failed"].([]any)
	if len(failed) != 1 || failed[0].(map[string]any)["id"] != "missing" {
		t.Fatalf("failed %v", failed)
	}
	for _, athleteData := range []string{"height_cm", "Bar position", "Lift profile", "Athlete context"} {
		if user := asked[0]["messages"].([]any)[1].(map[string]any)["content"].(string); strings.Contains(user, athleteData) {
			t.Fatalf("generic prompt carries athlete data %q: %s", athleteData, user)
		}
	}
	shared := h.catalog(t, "g1")
	if shared["generic_status"] != "ready" || shared["fatigue_profile_source"] != "ai_generic" || shared["description"] != "Sets up" || shared["how_to_perform"] != "1. Pull" {
		t.Fatalf("catalog %v", shared)
	}
	if _, pending := shared["generic_pending"]; pending {
		t.Fatal("generic_pending not removed")
	}
	if shared["primary_muscles"].([]any)[0] != "lats" || shared["lift_transfer"].(map[string]any)["source"] != "ai" {
		t.Fatalf("catalog %v", shared)
	}
	if h.catalog(t, "g2")["lift_transfer"].(map[string]any)["source"] != "user" || h.catalog(t, "g2")["generic_status"] != "ready" {
		t.Fatalf("g2 %v", h.catalog(t, "g2"))
	}
	if pending, _ := h.store.Pending(t.Context(), 5); len(pending) != 0 {
		t.Fatalf("index not empty: %v", pending)
	}
	for athlete, want := range map[string]string{"a1": "6", "a2": "9"} {
		if version, _ := h.redis.Get("pl:analysis-version:" + athlete); version != want {
			t.Fatalf("%s version %q want %s", athlete, version, want)
		}
	}
	if h.redis.Exists("pl:analysis:a2:section") {
		t.Fatal("analysis keys survived catalog change")
	}
}

func TestGenericEstimateSkipsNonPendingWithoutInference(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "done", "Done", nil)
	result, asked := h.drive(t, "glossary_generic_estimate", map[string]any{"ids": []any{"done"}}, person)
	if len(asked) != 0 || len(result["skipped"].([]any)) != 1 || len(result["saved"].([]any)) != 0 {
		t.Fatalf("result %v", result)
	}
}

func TestGenericEstimateCountsAttemptOnlyForRejectedItems(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.seedCatalog(t, "g2", "Other Lift", map[string]any{"generic_status": "pending", "generic_pending": "1", "generic_attempts": 0.0})
	good := map[string]any{"fatigue": map[string]any{"axial": 0.1, "neural": 0.1, "peripheral": 0.1, "systemic": 0.1, "reasoning": "x"}, "lift_transfer": map[string]any{"squat": 0.1, "bench": 0.1, "deadlift": 0.1, "reasoning": "x"}, "muscles": map[string]any{"primary_muscles": []any{"lats"}, "secondary_muscles": []any{}, "tertiary_muscles": []any{}, "reasoning": "x"}, "text": map[string]any{"description": "d", "how_to_perform": "h", "why_do_it": "w"}}
	result, _ := h.drive(t, "glossary_generic_estimate", map[string]any{"ids": []any{"g1", "g2"}}, person, answer(element("g1", good)))
	if len(result["saved"].([]any)) != 1 || len(result["failed"].([]any)) != 1 {
		t.Fatalf("result %v", result)
	}
	if h.catalog(t, "g1")["generic_status"] != "ready" || h.catalog(t, "g2")["generic_attempts"] != 1.0 || h.catalog(t, "g2")["generic_status"] != "pending" {
		t.Fatalf("g1 %v g2 %v", h.catalog(t, "g1"), h.catalog(t, "g2"))
	}
}

func TestGenericEstimateFailureCountsAttemptsThenFallsBackToDefault(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	for attempt := 1; attempt <= 3; attempt++ {
		h.svc.Generic.Fail(t.Context(), "g1")
		shared := h.catalog(t, "g1")
		if shared["generic_attempts"] != float64(attempt) {
			t.Fatalf("attempt %d: %v", attempt, shared)
		}
		_, pending := shared["generic_pending"]
		if (attempt < 3) != pending {
			t.Fatalf("attempt %d pending=%v", attempt, pending)
		}
	}
	shared := h.catalog(t, "g1")
	if shared["generic_status"] != "failed" || shared["fatigue_profile_source"] != "default" {
		t.Fatalf("catalog %v", shared)
	}
}

func TestTickSubmitsOneJobForAllPendingExercisesAsTheFirstCreator(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.store.CreateCatalog(t.Context(), map[string]any{"id": "g3", "name_key": "third", "created_at": "2026-02-01", "generic_pending": "1", "generic_status": "pending", "generic_attempts": 0.0, "created_by": "a9"})
	h.svc.Generic.Tick(t.Context())
	h.svc.Generic.Tick(t.Context())
	if len(h.coach.submissions) != 1 {
		t.Fatalf("submissions %d", len(h.coach.submissions))
	}
	submitted := h.coach.submissions[0]
	ids, _ := submitted.Arguments["ids"].([]any)
	if submitted.Operation != "glossary_generic_estimate" || submitted.Athlete != "a1" || submitted.Person != "p1" || len(ids) != 2 || ids[0] != "g1" || ids[1] != "g3" {
		t.Fatalf("submission %+v", submitted)
	}
	h.svc.Generic.Done("g1")
	h.svc.Generic.Done("g3")
	h.svc.Generic.Tick(t.Context())
	if len(h.coach.submissions) != 2 {
		t.Fatal("finished job not retried while still pending")
	}
}

func TestTickCountsSubmitFailureAndMissingCreator(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.coach.fail = errTest
	h.svc.Generic.Tick(t.Context())
	if h.catalog(t, "g1")["generic_attempts"] != 1.0 {
		t.Fatalf("catalog %v", h.catalog(t, "g1"))
	}
	pendingCatalog2 := map[string]any{"id": "g2", "name_key": "other", "created_at": "2026-02-01", "generic_pending": "1", "generic_status": "pending", "generic_attempts": 0.0}
	if created, _ := h.store.CreateCatalog(t.Context(), pendingCatalog2); !created {
		t.Fatal("seed")
	}
	h.svc.Generic.Tick(t.Context())
	if h.catalog(t, "g2")["generic_attempts"] != 1.0 || len(h.coach.submissions) != 2 {
		t.Fatalf("g2 %v submissions %d", h.catalog(t, "g2"), len(h.coach.submissions))
	}
}

func TestGenericEstimateTimeoutThroughExecutionRecordsAttempt(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.svc.Executions.Deadline = 100 * time.Millisecond
	h.svc.Generic.Tick(t.Context())
	caller := auth.Caller{Person: "p1", Athlete: "a1", JobID: "job_1"}
	if _, err := h.svc.Call(t.Context(), "glossary_generic_estimate", map[string]any{"ids": []any{"g1"}}, caller); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) && h.catalog(t, "g1")["generic_attempts"] == 0.0 {
		time.Sleep(10 * time.Millisecond)
	}
	if h.catalog(t, "g1")["generic_attempts"] != 1.0 {
		t.Fatalf("catalog %v", h.catalog(t, "g1"))
	}
	h.svc.Generic.Tick(t.Context())
	if len(h.coach.submissions) != 2 {
		t.Fatalf("failed job not released for retry: %d submissions", len(h.coach.submissions))
	}
}
