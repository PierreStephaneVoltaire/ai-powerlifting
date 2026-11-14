package service

import (
	"strings"
	"testing"

	"powerlifting/glossary-go/internal/auth"
)

var fatigueAnswer = map[string]any{"axial": 0.62, "neural": 0.5, "peripheral": 0.4, "systemic": 0.33, "reasoning": "hinge"}

func TestPersonalFatigueWritesOverlayAndQueuesGenericEstimate(t *testing.T) {
	h := newHarness(t)
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x1", "name": "Pause Squat", "category": "squat", "description": "slow"}})
	result, asked := h.drive(t, "glossary_estimate_fatigue", map[string]any{"id": "x1"}, person, fatigueAnswer)
	if toolName(asked[0]) != "estimate_fatigue_profile" || !strings.Contains(prompt(asked[0]), "height_cm: 180") || !strings.Contains(prompt(asked[0]), "Bar position: Low") {
		t.Fatalf("prompt %v", prompt(asked[0]))
	}
	personal := result["fatigue_profile"].(map[string]any)
	if personal["axial"] != 0.6 || personal["systemic"] != 0.35 || result["generic_status"] != "pending" {
		t.Fatalf("result %v", result)
	}
	overlay := h.overlay(t, "a1", "x1")
	if overlay["fatigue_profile_source"] != "ai_personal" || overlay["fatigue_profile_reasoning"] != "hinge" || overlay["estimated_at"] == nil {
		t.Fatalf("overlay %v", overlay)
	}
	shared := h.catalog(t, "x1")
	if shared["generic_status"] != "pending" || shared["generic_pending"] != "1" || shared["created_by"] != "a1" || shared["created_by_person"] != "p1" {
		t.Fatalf("catalog %v", shared)
	}
	for _, leaked := range []string{"fatigue_profile", "e1rm_estimate", "archived", "custom"} {
		if _, present := shared[leaked]; present {
			t.Fatalf("catalog carries %s: %v", leaked, shared)
		}
	}
	if version, _ := h.redis.Get("pl:analysis-version:a1"); version != "2" {
		t.Fatalf("analysis version %q", version)
	}
}

func TestPersonalFatigueReturnsExistingGenericAndRequeuesFailed(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"fatigue_profile": map[string]any{"axial": 0.8}, "generic_status": "failed", "generic_attempts": 3.0})
	result, _ := h.drive(t, "glossary_estimate_fatigue", map[string]any{"id": "sq"}, person, fatigueAnswer)
	if result["generic_fatigue_profile"].(map[string]any)["axial"] != 0.8 || result["generic_status"] != "pending" {
		t.Fatalf("result %v", result)
	}
	shared := h.catalog(t, "sq")
	if shared["generic_status"] != "pending" || shared["generic_pending"] != "1" || shared["generic_attempts"] != 0.0 {
		t.Fatalf("catalog %v", shared)
	}
	listed := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))["sq"]
	if listed["fatigue_profile_personalized"] != true || listed["generic_fatigue_profile"].(map[string]any)["axial"] != 0.8 {
		t.Fatalf("listed %v", listed)
	}
}

func TestPersonalFatigueLeavesReadyGenericAlone(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"fatigue_profile": map[string]any{"axial": 0.8}})
	result, _ := h.drive(t, "glossary_estimate_fatigue", map[string]any{"id": "sq"}, person, fatigueAnswer)
	if result["generic_status"] != "ready" {
		t.Fatalf("result %v", result)
	}
	if _, pending := h.catalog(t, "sq")["generic_pending"]; pending {
		t.Fatal("ready catalog entry requeued")
	}
}

func TestMusclesGoToCatalogWhenPresentAndClearOverride(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"primary_muscles": []any{"core"}})
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "sq", "name": "Squat", "primary_muscles": []any{"calves"}}})
	answer := map[string]any{"primary_muscles": []any{"quads", "lower_back"}, "secondary_muscles": []any{"quads", "glutes"}, "tertiary_muscles": []any{"core"}, "reasoning": "r"}
	result, _ := h.drive(t, "glossary_estimate_muscles", map[string]any{"id": "sq"}, person, answer)
	if got := result["primary_muscles"].([]any); len(got) != 2 || got[1] != "lower_back" {
		t.Fatalf("primary %v", got)
	}
	if got := result["secondary_muscles"].([]any); len(got) != 1 || got[0] != "glutes" {
		t.Fatalf("deduplicated secondary %v", got)
	}
	if got := h.catalog(t, "sq")["primary_muscles"].([]any); got[0] != "quads" {
		t.Fatalf("catalog %v", got)
	}
	if _, overridden := h.overlay(t, "a1", "sq")["primary_muscles"]; overridden {
		t.Fatal("overlay override still shadows the new estimate")
	}
}

func TestMusclesGoToOverlayForCustomExercise(t *testing.T) {
	h := newHarness(t)
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x1", "name": "Odd Lift"}})
	answer := map[string]any{"primary_muscles": []any{"lats"}, "secondary_muscles": []any{}, "tertiary_muscles": []any{}, "reasoning": "r"}
	h.drive(t, "glossary_estimate_muscles", map[string]any{"id": "x1"}, person, answer)
	if h.overlay(t, "a1", "x1")["primary_muscles"].([]any)[0] != "lats" || h.catalog(t, "x1") != nil {
		t.Fatal("custom exercise definition not kept on the overlay")
	}
}

func TestLiftTransferStoredWithIDAndOnlyReturnedInline(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	answer := map[string]any{"squat": 0.93, "bench": 0.0, "deadlift": 0.2, "reasoning": " same pattern "}
	result, _ := h.drive(t, "glossary_estimate_lift_transfer", map[string]any{"id": "sq"}, person, answer)
	transfer := result["lift_transfer"].(map[string]any)
	if transfer["squat"] != 0.95 || transfer["source"] != "ai" || transfer["reasoning"] != "same pattern" {
		t.Fatalf("transfer %v", transfer)
	}
	if h.catalog(t, "sq")["lift_transfer"] == nil {
		t.Fatal("not stored on catalog")
	}
	inline, _ := h.drive(t, "glossary_estimate_lift_transfer", map[string]any{"exercise": map[string]any{"name": "Anything"}}, person, answer)
	if _, stored := inline["id"]; stored || h.catalog(t, "sq")["name"] != "Squat" {
		t.Fatalf("inline result %v", inline)
	}
}

func TestGenerateTextIsReturnedNotStored(t *testing.T) {
	h := newHarness(t)
	answer := map[string]any{"description": "  A  squat\nvariation ", "how_to_perform": "1. Set up", "why_do_it": "Builds legs"}
	result, asked := h.drive(t, "glossary_generate_text", map[string]any{"exercise": map[string]any{"name": "Pause Squat"}}, person, answer)
	if result["description"] != "A squat variation" || result["status"] != "generated" {
		t.Fatalf("result %v", result)
	}
	if !strings.Contains(prompt(asked[0]), "squat: Bar position: Low") {
		t.Fatalf("lift profiles missing from prompt %v", prompt(asked[0]))
	}
	if h.overlay(t, "a1", "x1") != nil {
		t.Fatal("generate text wrote")
	}
}

func TestE1RMEstimateIsPersonal(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	answer := map[string]any{"estimates": []any{map[string]any{"exercise": "Squat", "e1rm_kg": 180.0, "ratio": 0.9, "primary_lift_used": "squat", "basis": "history", "confidence": "medium"}}}
	result, asked := h.drive(t, "glossary_estimate_e1rm", map[string]any{"id": "sq"}, person, answer)
	if result["status"] != "estimated" || result["estimate"].(map[string]any)["e1rm_kg"] != 180.0 {
		t.Fatalf("result %v", result)
	}
	if !strings.Contains(prompt(asked[0]), "2026-01-01") {
		t.Fatal("past instances missing from prompt")
	}
	stored := h.overlay(t, "a1", "sq")["e1rm_estimate"].(map[string]any)
	if stored["value_kg"] != 180.0 || stored["method"] != "ai_backfill" || stored["manually_overridden"] != false {
		t.Fatalf("stored %v", stored)
	}
	if _, shared := h.catalog(t, "sq")["e1rm_estimate"]; shared {
		t.Fatal("personal e1rm reached catalog")
	}
}

func TestEstimateRejectsAnswerThatFailsToolSchema(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	caller := person
	caller.JobID = "job_1"
	response, err := h.svc.Call(t.Context(), "glossary_estimate_fatigue", map[string]any{"id": "sq"}, caller)
	if err != nil {
		t.Fatal(err)
	}
	body := response.Body.(map[string]any)
	_, err = h.svc.Resume(t.Context(), body["execution_id"].(string), map[string]any{"challenge_id": body["challenge_id"], "content": map[string]any{"axial": 0.5}}, caller)
	if err == nil {
		t.Fatal("incomplete tool answer accepted")
	}
}

func TestAIWithoutJobSubmitsCoachJobAndNeedsPerson(t *testing.T) {
	h := newHarness(t)
	response, err := h.svc.Call(t.Context(), "glossary_estimate_fatigue", map[string]any{"id": "sq"}, person)
	if err != nil || response.Status != 202 {
		t.Fatalf("response %+v err %v", response, err)
	}
	submitted := h.coach.submissions[0]
	if submitted.Operation != "glossary_estimate_fatigue" || submitted.Athlete != "a1" || submitted.Person != "p1" || submitted.Arguments["id"] != "sq" {
		t.Fatalf("submission %+v", submitted)
	}
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_fatigue", map[string]any{"id": "sq"}, auth.Caller{Athlete: "a1"}); err == nil {
		t.Fatal("anonymous submit accepted")
	}
}

func TestUnknownExerciseFailsBeforeInference(t *testing.T) {
	h := newHarness(t)
	caller := person
	caller.JobID = "job_1"
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_muscles", map[string]any{"id": "nope"}, caller); err == nil {
		t.Fatal("unknown id started an execution")
	}
}

func TestNestedAIOperationIsRefused(t *testing.T) {
	h := newHarness(t)
	caller := person
	caller.JobID, caller.Nested = "job_1", true
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_muscles", map[string]any{"id": "sq"}, caller); err == nil {
		t.Fatal("nested AI accepted")
	}
}
