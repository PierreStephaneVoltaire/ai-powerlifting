package contract

import "testing"

func TestRegistryHoldsTheFiveCompetitionOperations(t *testing.T) {
	registry, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"calculate_attempts", "health_list_competitions", "health_update_user_competition", "health_complete_user_competition", "health_snapshot_competition_projection"}
	got := registry.All()
	if len(got) != len(want) {
		t.Fatalf("got %d operations", len(got))
	}
	for index, name := range want {
		if got[index].Name != name {
			t.Errorf("operation %d is %s, want %s", index, got[index].Name, name)
		}
		if got[index].InternalOnly {
			t.Errorf("%s must not be internal-only", name)
		}
		if !got[index].HasInput("pk") {
			t.Errorf("%s lacks the pk input", name)
		}
	}
}

func TestInputAndResultValidation(t *testing.T) {
	registry, _ := Load()
	attempts, _ := registry.Get("calculate_attempts")
	if err := attempts.ValidateInput(map[string]any{"lift": "squat", "opener_kg": 100.0, "pk": "a"}); err != nil {
		t.Fatal(err)
	}
	for name, arguments := range map[string]map[string]any{
		"bad lift":  {"lift": "snatch", "opener_kg": 100.0},
		"zero":      {"lift": "squat", "opener_kg": 0.0},
		"negative":  {"lift": "squat", "opener_kg": 100.0, "j1_override": -1.0},
		"bad felt":  {"lift": "squat", "opener_kg": 100.0, "last_felt": "tired"},
		"empty pk":  {"lift": "squat", "opener_kg": 100.0, "pk": ""},
		"no opener": {"lift": "squat"},
	} {
		if attempts.ValidateInput(arguments) == nil {
			t.Errorf("%s accepted", name)
		}
	}
	if attempts.ValidateResult(map[string]any{"lift": "squat"}) == nil {
		t.Error("incomplete result accepted")
	}
	snapshot, _ := registry.Get("health_snapshot_competition_projection")
	if snapshot.ValidateInput(map[string]any{"date": "2027-04-24"}) != nil || snapshot.ValidateInput(map[string]any{"date": "short"}) == nil {
		t.Error("date length not enforced")
	}
}
