package service

import (
	"strings"
	"testing"

	"powerlifting/glossary/internal/auth"
)

var fatigueAnswer = map[string]any{"axial": 0.62, "neural": 0.5, "peripheral": 0.4, "systemic": 0.33, "reasoning": "hinge"}

var musclesAnswer = map[string]any{"primary_muscles": []any{"quads", "lower_back"}, "secondary_muscles": []any{"quads", "glutes"}, "tertiary_muscles": []any{"core"}, "reasoning": "r"}

var transferAnswer = map[string]any{"squat": 0.93, "bench": 0.0, "deadlift": 0.2, "reasoning": " same pattern "}

var e1rmAnswer = map[string]any{"e1rm_kg": 180.0, "ratio": 0.9, "primary_lift_used": "squat", "basis": "history", "confidence": "medium"}

func batch(ids []any, aspects ...any) map[string]any {
	return map[string]any{"ids": ids, "aspects": aspects}
}

func answer(results ...map[string]any) map[string]any {
	list := make([]any, 0, len(results))
	for _, result := range results {
		list = append(list, result)
	}
	return map[string]any{"results": list}
}

func element(id string, fields map[string]any) map[string]any {
	fields["id"] = id
	return fields
}

func TestBatchOfFatigueSavesEachPersonallyAndQueuesGenericOnce(t *testing.T) {
	h := newHarness(t)
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x1", "name": "Pause Squat", "category": "squat", "description": "slow"}})
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x2", "name": "Row"}})
	h.seedCatalog(t, "sq", "Squat", map[string]any{"fatigue_profile": map[string]any{"axial": 0.8}, "generic_status": "failed", "generic_attempts": 3.0})
	h.redis.Set("pl:analysis-version:a1", "0")
	h.redis.Set("pl:analysis-version:a2", "8")
	result, asked := h.drive(t, "glossary_estimate_batch", batch([]any{"x1", "x2", "sq"}, "fatigue"), person,
		answer(element("x1", map[string]any{"fatigue": fatigueAnswer}), element("x2", map[string]any{"fatigue": fatigueAnswer}), element("sq", map[string]any{"fatigue": fatigueAnswer})))
	if len(asked) != 1 || toolName(asked[0]) != "report_exercise_estimates" {
		t.Fatalf("asked %d calls", len(asked))
	}
	user := prompt(asked[0])
	if strings.Count(user, "height_cm: 180") != 1 || strings.Count(user, "Bar position: Low") != 1 || !strings.Contains(user, "Pause Squat") || !strings.Contains(user, "Row") {
		t.Fatalf("prompt %v", user)
	}
	if len(result["saved"].([]any)) != 3 || len(result["failed"].([]any)) != 0 {
		t.Fatalf("result %v", result)
	}
	overlay := h.overlay(t, "a1", "x1")
	if overlay["fatigue_profile_source"] != "ai_personal" || overlay["fatigue_profile_reasoning"] != "hinge" || overlay["estimated_at"] == nil || overlay["fatigue_profile"].(map[string]any)["axial"] != 0.6 {
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
	requeued := h.catalog(t, "sq")
	if requeued["generic_status"] != "pending" || requeued["generic_pending"] != "1" || requeued["generic_attempts"] != 0.0 {
		t.Fatalf("catalog %v", requeued)
	}
	listed := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))["sq"]
	if listed["fatigue_profile_personalized"] != true || listed["generic_fatigue_profile"].(map[string]any)["axial"] != 0.8 {
		t.Fatalf("listed %v", listed)
	}
	if version, _ := h.redis.Get("pl:analysis-version:a1"); version != "2" {
		t.Fatalf("athlete analysis version %q", version)
	}
	if version, _ := h.redis.Get("pl:analysis-version:a2"); version != "9" {
		t.Fatalf("catalog invalidated %q times", version)
	}
}

func TestBatchLeavesReadyGenericAlone(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"fatigue_profile": map[string]any{"axial": 0.8}})
	h.drive(t, "glossary_estimate_batch", batch([]any{"sq"}, "fatigue"), person, answer(element("sq", map[string]any{"fatigue": fatigueAnswer})))
	if _, pending := h.catalog(t, "sq")["generic_pending"]; pending {
		t.Fatal("ready catalog entry requeued")
	}
}

func TestBatchDefinitionsGoToCatalogWhenPresentAndOverlayOtherwise(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"primary_muscles": []any{"core"}})
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "sq", "name": "Squat", "primary_muscles": []any{"calves"}}})
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x1", "name": "Odd Lift"}})
	text := map[string]any{"description": "A squat", "how_to_perform": "1. Set up", "why_do_it": "Legs"}
	result, _ := h.drive(t, "glossary_estimate_batch", batch([]any{"sq", "x1"}, "muscles", "lift_transfer", "text"), person, answer(
		element("sq", map[string]any{"muscles": musclesAnswer, "lift_transfer": transferAnswer, "text": text}),
		element("x1", map[string]any{"muscles": musclesAnswer, "lift_transfer": transferAnswer, "text": text}),
	))
	if len(result["saved"].([]any)) != 2 {
		t.Fatalf("result %v", result)
	}
	shared := h.catalog(t, "sq")
	if shared["primary_muscles"].([]any)[0] != "quads" || len(shared["secondary_muscles"].([]any)) != 1 || shared["lift_transfer"].(map[string]any)["squat"] != 0.95 || shared["description"] != "A squat" {
		t.Fatalf("catalog %v", shared)
	}
	if _, overridden := h.overlay(t, "a1", "sq")["primary_muscles"]; overridden {
		t.Fatal("overlay override still shadows the new estimate")
	}
	custom := h.overlay(t, "a1", "x1")
	if custom["primary_muscles"].([]any)[0] != "quads" || custom["how_to_perform"] != "1. Set up" || custom["lift_transfer"].(map[string]any)["source"] != "ai" || h.catalog(t, "x1") != nil {
		t.Fatalf("custom overlay %v", custom)
	}
}

func TestBatchE1RMIsPersonal(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	_, asked := h.drive(t, "glossary_estimate_batch", batch([]any{"sq"}, "e1rm"), person, answer(element("sq", map[string]any{"e1rm": e1rmAnswer})))
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

func TestBatchReportsMissingAndInvalidElementsWithoutFailingTheRest(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "good", "Good", nil)
	h.seedCatalog(t, "bad", "Bad", nil)
	h.seedCatalog(t, "gone", "Gone", nil)
	result, _ := h.drive(t, "glossary_estimate_batch", batch([]any{"good", "bad", "gone", "nope"}, "fatigue"), person, answer(
		element("good", map[string]any{"fatigue": fatigueAnswer}),
		element("bad", map[string]any{"fatigue": map[string]any{"axial": 0.5}}),
	))
	if saved := result["saved"].([]any); len(saved) != 1 || saved[0] != "good" {
		t.Fatalf("saved %v", saved)
	}
	reasons := map[string]string{}
	for _, item := range result["failed"].([]any) {
		reasons[item.(map[string]any)["id"].(string)] = item.(map[string]any)["reason"].(string)
	}
	if len(reasons) != 3 || reasons["gone"] != "missing from model response" || reasons["bad"] == "" || !strings.Contains(reasons["nope"], "not found") {
		t.Fatalf("reasons %v", reasons)
	}
	if h.overlay(t, "a1", "bad") != nil || h.overlay(t, "a1", "gone") != nil {
		t.Fatal("failed elements were written")
	}
}

func TestBatchRejectsAnswerThatFailsToolSchema(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	caller := person
	caller.JobID = "job_1"
	response, err := h.svc.Call(t.Context(), "glossary_estimate_batch", batch([]any{"sq"}, "fatigue"), caller)
	if err != nil {
		t.Fatal(err)
	}
	body := response.Body.(map[string]any)
	_, err = h.svc.Resume(t.Context(), body["execution_id"].(string), map[string]any{"challenge_id": body["challenge_id"], "content": map[string]any{"results": []any{map[string]any{"id": "other"}}}}, caller)
	if err == nil {
		t.Fatal("answer for an unrequested id accepted")
	}
}

func TestBatchInputIsBounded(t *testing.T) {
	h := newHarness(t)
	ids := make([]any, 26)
	for index := range ids {
		ids[index] = "x"
	}
	h.fail(t, "glossary_estimate_batch", batch(ids, "fatigue"), 422)
	h.fail(t, "glossary_estimate_batch", batch([]any{"sq"}, "bogus"), 422)
	h.fail(t, "glossary_estimate_batch", batch([]any{}, "fatigue"), 422)
}

func TestAIWithoutJobSubmitsCoachJobAndNeedsPerson(t *testing.T) {
	h := newHarness(t)
	response, err := h.svc.Call(t.Context(), "glossary_estimate_batch", batch([]any{"sq"}, "fatigue"), person)
	if err != nil || response.Status != 202 {
		t.Fatalf("response %+v err %v", response, err)
	}
	submitted := h.coach.submissions[0]
	if submitted.Operation != "glossary_estimate_batch" || submitted.Athlete != "a1" || submitted.Person != "p1" || submitted.Arguments["ids"].([]any)[0] != "sq" {
		t.Fatalf("submission %+v", submitted)
	}
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_batch", batch([]any{"sq"}, "fatigue"), auth.Caller{Athlete: "a1"}); err == nil {
		t.Fatal("anonymous submit accepted")
	}
}

func TestUnknownExercisesFailBeforeInference(t *testing.T) {
	h := newHarness(t)
	caller := person
	caller.JobID = "job_1"
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_batch", batch([]any{"nope"}, "muscles"), caller); err == nil {
		t.Fatal("unknown id started an execution")
	}
}

func TestNestedAIOperationIsRefused(t *testing.T) {
	h := newHarness(t)
	caller := person
	caller.JobID, caller.Nested = "job_1", true
	if _, err := h.svc.Call(t.Context(), "glossary_estimate_batch", batch([]any{"sq"}, "muscles"), caller); err == nil {
		t.Fatal("nested AI accepted")
	}
}
