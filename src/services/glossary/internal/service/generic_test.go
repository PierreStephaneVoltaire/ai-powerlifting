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

var genericAnswers = []map[string]any{
	{"primary_muscles": []any{"lats"}, "secondary_muscles": []any{"biceps"}, "tertiary_muscles": []any{}, "reasoning": "pull"},
	{"description": "Ignored", "how_to_perform": "1. Pull", "why_do_it": "Back"},
	{"squat": 0.0, "bench": 0.0, "deadlift": 0.1, "reasoning": "low"},
	{"axial": 0.2, "neural": 0.3, "peripheral": 0.4, "systemic": 0.1, "reasoning": "light"},
}

func TestGenericEstimateFillsCatalogFromDefinitionOnly(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.redis.Set("pl:analysis-version:a1", "5")
	h.redis.Set("pl:analysis-version:a2", "8")
	h.redis.Set("pl:analysis:a2:section", "{}")
	creator := auth.Caller{Person: "p1", Athlete: "a1"}
	result, asked := h.drive(t, "glossary_generic_estimate", map[string]any{"id": "g1"}, creator, genericAnswers...)
	if result["status"] != "generic_estimated" || result["generic_status"] != "ready" {
		t.Fatalf("result %v", result)
	}
	for _, challenge := range asked {
		for _, athleteData := range []string{"height_cm", "Bar position", "Lift profile"} {
			if strings.Contains(prompt(challenge), athleteData) {
				t.Fatalf("generic prompt carries athlete data %q: %s", athleteData, prompt(challenge))
			}
		}
	}
	want := []string{"estimate_muscle_groups", "generate_glossary_text", "estimate_lift_transfer", "estimate_fatigue_profile"}
	for index, challenge := range asked {
		if toolName(challenge) != want[index] {
			t.Fatalf("call %d used %s", index, toolName(challenge))
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

func TestGenericEstimateSkipsNonPendingAndKeepsUserLiftTransfer(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "done", "Done", nil)
	result, asked := h.drive(t, "glossary_generic_estimate", map[string]any{"id": "done"}, person)
	if result["status"] != "skipped" || len(asked) != 0 {
		t.Fatalf("result %v", result)
	}
	pendingCatalog(h, t, map[string]any{"primary_muscles": []any{"lats"}, "how_to_perform": "x", "why_do_it": "y", "lift_transfer": map[string]any{"squat": 0.5, "bench": 0.0, "deadlift": 0.0, "source": "user", "reasoning": "mine"}})
	_, asked = h.drive(t, "glossary_generic_estimate", map[string]any{"id": "g1"}, person, genericAnswers[3])
	if len(asked) != 1 || h.catalog(t, "g1")["lift_transfer"].(map[string]any)["source"] != "user" {
		t.Fatalf("asked %d", len(asked))
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

func TestTickSubmitsEachPendingExerciseOnceAsItsCreator(t *testing.T) {
	h := newHarness(t)
	pendingCatalog(h, t, nil)
	h.svc.Generic.Tick(t.Context())
	h.svc.Generic.Tick(t.Context())
	if len(h.coach.submissions) != 1 {
		t.Fatalf("submissions %d", len(h.coach.submissions))
	}
	submitted := h.coach.submissions[0]
	if submitted.Operation != "glossary_generic_estimate" || submitted.Athlete != "a1" || submitted.Person != "p1" || submitted.Arguments["id"] != "g1" {
		t.Fatalf("submission %+v", submitted)
	}
	h.svc.Generic.Done("g1")
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
	if _, err := h.svc.Call(t.Context(), "glossary_generic_estimate", map[string]any{"id": "g1"}, caller); err != nil {
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
