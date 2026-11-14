package service

import (
	"reflect"
	"testing"

	"powerlifting/glossary-go/internal/auth"
)

func exercises(body map[string]any) map[string]map[string]any {
	out := map[string]map[string]any{}
	for _, entry := range body["exercises"].([]any) {
		item := entry.(map[string]any)
		out[item["id"].(string)] = item
	}
	return out
}

func TestUpsertCreatesCustomOverlayWithRuleLiftTransfer(t *testing.T) {
	h := newHarness(t)
	result := h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x1", "name": " Pause Squat ", "primary_muscles": []any{"quads"}}})
	if result["status"] != "upserted" || result["id"] != "x1" {
		t.Fatalf("result %v", result)
	}
	overlay := h.overlay(t, "a1", "x1")
	if overlay["custom"] != true || overlay["name"] != "Pause Squat" || overlay["name_key"] != "pause squat" || overlay["created_by"] != "a1" || overlay["created_by_person"] != "p1" {
		t.Fatalf("overlay %v", overlay)
	}
	if transfer := overlay["lift_transfer"].(map[string]any); transfer["source"] != "rule" || transfer["squat"] != 0.9 {
		t.Fatalf("transfer %v", transfer)
	}
	if h.catalog(t, "x1") != nil {
		t.Fatal("request path wrote the catalog")
	}
	listed := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))
	if listed["x1"]["custom"] != true {
		t.Fatalf("listed %v", listed)
	}
}

func TestUpsertGeneratesIDWhenMissingAndRejectsEmptyName(t *testing.T) {
	h := newHarness(t)
	id := h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"name": "Row"}})["id"].(string)
	if id == "" || h.overlay(t, "a1", id) == nil {
		t.Fatal("no generated id")
	}
	h.fail(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"name": "  "}}, 422)
}

func TestGlossaryMergesCatalogWithAthleteOverlayOnly(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"description": "shared", "fatigue_profile": map[string]any{"axial": 0.8}, "fatigue_profile_source": "ai_generic"})
	h.seedCatalog(t, "bp", "Bench", nil)
	h.call(t, "exercise_archive", map[string]any{"id": "sq"})
	mine := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))
	if len(mine) != 2 || mine["sq"]["archived"] != true || mine["sq"]["fatigue_profile_personalized"] != false {
		t.Fatalf("mine %v", mine)
	}
	other, _ := h.svc.Call(t.Context(), "exercise_get_glossary", map[string]any{}, auth.Caller{Person: "p2", Athlete: "a2"})
	theirs := exercises(other.Body.(map[string]any))
	if _, archived := theirs["sq"]["archived"]; archived || len(theirs) != 2 {
		t.Fatalf("overlay leaked to another athlete: %v", theirs)
	}
}

func TestUpsertOnCatalogExerciseStoresOnlyChangedFields(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"description": "shared", "primary_muscles": []any{"quads"}, "fatigue_profile": map[string]any{"axial": 0.8}, "fatigue_profile_source": "ai_generic"})
	effective := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))["sq"]
	effective["description"] = "my cue"
	h.call(t, "exercise_upsert", map[string]any{"exercise": effective})
	overlay := h.overlay(t, "a1", "sq")
	if overlay["description"] != "my cue" {
		t.Fatalf("overlay %v", overlay)
	}
	for _, key := range []string{"fatigue_profile", "primary_muscles", "name", "custom"} {
		if _, stored := overlay[key]; stored {
			t.Fatalf("%s copied into overlay: %v", key, overlay)
		}
	}
	if h.catalog(t, "sq")["description"] != "shared" {
		t.Fatal("catalog changed by athlete edit")
	}
}

func TestUpsertNameHandling(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", map[string]any{"description": "shared"})
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x9", "name": "Bench"}})
	merged := h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "new", "name": "SQUAT", "description": ""}})
	if merged["id"] != "sq" || h.overlay(t, "a1", "new") != nil {
		t.Fatalf("same name did not merge: %v", merged)
	}
	if overlay := h.overlay(t, "a1", "sq"); overlay != nil && overlay["description"] == "" {
		t.Fatalf("empty payload field overwrote shared text: %v", overlay)
	}
	h.fail(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"id": "x9", "name": "squat"}}, 409)
}

func TestRemoveHidesWithoutDeletingAndUpsertRestores(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	h.call(t, "exercise_remove", map[string]any{"id": "sq"})
	if _, present := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))["sq"]; present {
		t.Fatal("hidden exercise still listed")
	}
	if h.catalog(t, "sq") == nil {
		t.Fatal("catalog exercise deleted")
	}
	h.call(t, "exercise_upsert", map[string]any{"exercise": map[string]any{"name": "Squat"}})
	if _, present := exercises(h.call(t, "exercise_get_glossary", map[string]any{}))["sq"]; !present {
		t.Fatal("upsert did not restore")
	}
}

func TestSetE1RMStaysPersonalAndUnknownIDsAreRejected(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	result := h.call(t, "exercise_set_e1rm", map[string]any{"id": "sq", "value_kg": 210.5})
	if result["method"] != "manual" || result["value_kg"] != 210.5 {
		t.Fatalf("result %v", result)
	}
	estimate := h.overlay(t, "a1", "sq")["e1rm_estimate"].(map[string]any)
	if estimate["manually_overridden"] != true || estimate["confidence"] != "medium" || estimate["basis"] != "Manual entry" {
		t.Fatalf("estimate %v", estimate)
	}
	if _, shared := h.catalog(t, "sq")["e1rm_estimate"]; shared {
		t.Fatal("e1rm written to catalog")
	}
	h.fail(t, "exercise_set_e1rm", map[string]any{"id": "missing", "value_kg": 1.0}, 404)
	h.fail(t, "exercise_archive", map[string]any{"id": "missing"}, 404)
}

func TestWritesBumpAnalysisAndDropBackendGlossaryCache(t *testing.T) {
	h := newHarness(t)
	h.seedCatalog(t, "sq", "Squat", nil)
	h.redis.Set("pl:cache:a1:item:%2Fexercises", "{}")
	h.redis.Set("pl:cache:a1:idx:%2Fexercises", "x")
	h.redis.SAdd("pl:cache:a1:domain:glossary", "pl:cache:a1:item:%2Fexercises")
	h.call(t, "exercise_archive", map[string]any{"id": "sq"})
	if version, _ := h.redis.Get("pl:analysis-version:a1"); version != "1" {
		t.Fatalf("analysis version %q", version)
	}
	for _, key := range []string{"pl:cache:a1:item:%2Fexercises", "pl:cache:a1:idx:%2Fexercises", "pl:cache:a1:domain:glossary"} {
		if h.redis.Exists(key) {
			t.Fatalf("%s survived", key)
		}
	}
	h.call(t, "exercise_get_glossary", map[string]any{})
	if version, _ := h.redis.Get("pl:analysis-version:a1"); version != "1" {
		t.Fatal("read bumped analysis version")
	}
}

func TestInputIsScopedToCaller(t *testing.T) {
	h := newHarness(t)
	h.fail(t, "exercise_get_glossary", map[string]any{"pk": "someone-else"}, 403)
	h.fail(t, "exercise_get_glossary", map[string]any{"_access": map[string]any{}}, 403)
	if _, err := h.svc.Call(t.Context(), "exercise_get_glossary", map[string]any{}, auth.Caller{Person: "p1"}); err == nil {
		t.Fatal("call without athlete accepted")
	}
	if _, err := h.svc.Call(t.Context(), "no_such_op", map[string]any{}, person); err == nil {
		t.Fatal("unknown op accepted")
	}
	h.access.deny = 403
	h.fail(t, "exercise_get_glossary", map[string]any{}, 403)
	if !reflect.DeepEqual(h.access.seen[0], "exercise_get_glossary") {
		t.Fatalf("access seen %v", h.access.seen)
	}
}
