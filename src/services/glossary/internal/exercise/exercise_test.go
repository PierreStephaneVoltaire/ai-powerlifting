package exercise

import (
	"reflect"
	"testing"
)

func TestNameKeyFoldsCaseAndWhitespace(t *testing.T) {
	if got := NameKey("  Paused   BENCH Press "); got != "paused bench press" {
		t.Fatalf("got %q", got)
	}
}

func TestMergeLetsOverlayWinAndKeepsGenericFatigueSeparate(t *testing.T) {
	catalog := Item{"id": "e1", "name": "Squat", "description": "shared", "fatigue_profile": Item{"axial": 0.8}, "fatigue_profile_source": "ai_generic", "generic_status": "ready"}
	overlay := Item{"id": "e1", "description": "mine", "archived": true, "fatigue_profile": Item{"axial": 0.9}, "fatigue_profile_source": "ai_personal"}
	got := Merge(catalog, overlay)
	if got["description"] != "mine" || got["archived"] != true || got["name"] != "Squat" {
		t.Fatalf("merged %v", got)
	}
	if !reflect.DeepEqual(got["fatigue_profile"], Item{"axial": 0.9}) || !reflect.DeepEqual(got["generic_fatigue_profile"], Item{"axial": 0.8}) || got["fatigue_profile_personalized"] != true {
		t.Fatalf("fatigue %v", got)
	}
	if got["generic_status"] != "ready" || got["fatigue_profile_source"] != "ai_personal" {
		t.Fatalf("status %v", got)
	}
}

func TestMergeFallsBackToGenericFatigueWithoutPersonal(t *testing.T) {
	catalog := Item{"id": "e1", "fatigue_profile": Item{"axial": 0.8}, "fatigue_profile_source": "ai_generic"}
	got := Merge(catalog, nil)
	if !reflect.DeepEqual(got["fatigue_profile"], Item{"axial": 0.8}) || got["fatigue_profile_personalized"] != false || got["fatigue_profile_source"] != "ai_generic" {
		t.Fatalf("merged %v", got)
	}
}

func TestCleanKeepsOnlyWritableFieldsAndNormalises(t *testing.T) {
	cleaned := Clean(Item{
		"name": " Bench ", "description": "  text ", "primary_muscles": "chest", "video_url": "  ", "cues": "x",
		"generic_status": "ready", "generic_fatigue_profile": Item{}, "id": "e1", "archived": false,
	})
	want := Item{"name": "Bench", "description": "text", "primary_muscles": []any{}, "archived": false}
	if !reflect.DeepEqual(cleaned, want) {
		t.Fatalf("cleaned %v", cleaned)
	}
}

func TestDiffReportsOnlyChangedFields(t *testing.T) {
	effective := Item{"name": "Bench", "description": "a", "primary_muscles": []any{"chest"}}
	cleaned := Item{"name": "Bench", "description": "b", "primary_muscles": []any{"chest"}, "how_to_perform": ""}
	got := Diff(effective, cleaned, false)
	if !reflect.DeepEqual(got, Item{"description": "b"}) {
		t.Fatalf("diff %v", got)
	}
	if got := Diff(effective, Item{"description": ""}, true); len(got) != 0 {
		t.Fatalf("skipEmpty diff %v", got)
	}
	if got := Diff(effective, Item{"description": ""}, false); got["description"] != "" {
		t.Fatalf("explicit clear lost %v", got)
	}
}

func TestDefinitionDropsPersonalData(t *testing.T) {
	definition := Definition(Item{"id": "e1", "name": "Bench", "e1rm_estimate": Item{"value_kg": 1.0}, "fatigue_profile": Item{}, "archived": true, "description": "d"})
	if _, leaked := definition["e1rm_estimate"]; leaked {
		t.Fatal("e1rm leaked")
	}
	if _, leaked := definition["fatigue_profile"]; leaked {
		t.Fatal("fatigue leaked")
	}
	if definition["name_key"] != "bench" || definition["description"] != "d" {
		t.Fatalf("definition %v", definition)
	}
}

func TestRuleLiftTransfer(t *testing.T) {
	cases := []struct {
		item  Item
		lift  string
		value float64
		text  string
	}{
		{Item{"name": "Back Squat"}, "squat", 1, "Rule competition: squat 1.0"},
		{Item{"name": "Close-Grip Bench Press"}, "bench", 0.85, "Rule close_grip_bench: bench 0.85"},
		{Item{"name": "Paused Deadlift"}, "deadlift", 0.9, "Rule paused_variant: deadlift 0.9"},
		{Item{"name": "Romanian Deadlift"}, "deadlift", 0.6, "Rule hinge: deadlift 0.6"},
		{Item{"name": "Leg Curl", "primary_muscles": []any{"hamstrings"}}, "deadlift", 0.15, "Rule isolation: muscle-based default capped at 0.15"},
	}
	for _, tc := range cases {
		got := RuleLiftTransfer(tc.item)
		if got[tc.lift] != tc.value || got["source"] != "rule" || got["reasoning"] != tc.text {
			t.Errorf("%v: %v", tc.item["name"], got)
		}
	}
}
