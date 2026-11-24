package profile

import (
	"reflect"
	"testing"
)

func TestMuscleGroupsDeduplicateAcrossBuckets(t *testing.T) {
	got := MuscleGroups([]string{"Adductor", "front deltoids", "unknown", "chest"}, []string{"adductors", "lateral-delts", "chest", "lats"})
	want := [][]string{{"adductors", "front_delts", "chest"}, {"side_delts", "lats"}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %#v", got)
	}
}

func TestStimulus(t *testing.T) {
	for input, want := range map[float64]float64{1.23: 1.25, 0.4: 1, 3: 2} {
		if got := Stimulus(input); got != want {
			t.Fatalf("Stimulus(%v) = %v, want %v", input, got, want)
		}
	}
}

func TestRelatedLifts(t *testing.T) {
	if got := RelatedLifts("Paused Romanian Deadlift", "squat"); !reflect.DeepEqual(got, []string{"squat", "deadlift"}) {
		t.Fatalf("got %#v", got)
	}
	if got := RelatedLifts("curl", "arms"); len(got) != 0 {
		t.Fatalf("got %#v", got)
	}
}

func TestSelectProfilesOrdersRelatedFirst(t *testing.T) {
	related, got := SelectProfiles("RDL", "", []map[string]any{{"lift": "squat"}, {"lift": "bench"}, {"lift": "deadlift"}})
	if !reflect.DeepEqual(related, []string{"deadlift"}) || len(got) != 3 || got[0]["lift"] != "deadlift" || got[1]["lift"] != "squat" || got[2]["lift"] != "bench" {
		t.Fatalf("got %#v %#v", related, got)
	}
}

func TestAthleteContext(t *testing.T) {
	got := Athlete(map[string]any{"current_body_weight_kg": 84.5, "height_cm": float64(0), "body_fat_range": "15_20", "sex": ""})
	want := map[string]any{"bodyweight_kg": 84.5, "body_fat_range": "15 to 20%"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %#v", got)
	}
}
