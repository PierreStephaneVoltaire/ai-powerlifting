package orchestration

import "testing"

var models = Models{Fast: "fast", Standard: "std", Strong: "strong"}

func TestComplexityPicksTier(t *testing.T) {
	cases := map[string]Tier{"low": TierFast, "medium": TierStandard, "high": TierStrong}
	for complexity, want := range cases {
		if got := models.Resolve(complexity, "std"); got != want {
			t.Errorf("%s: got %v want %v", complexity, got, want)
		}
	}
	if models.Resolve("", "fast") != TierFast || models.Resolve("", "unknown") != TierStandard {
		t.Fatal("default model tier wrong")
	}
	if models.Model(TierStrong) != "strong" {
		t.Fatal("model lookup wrong")
	}
}

func TestEscalationMovesUpAndStops(t *testing.T) {
	next, ok := Escalate(TierFast, TierFast)
	if !ok || next != TierStandard {
		t.Fatalf("fast: %v %v", next, ok)
	}
	next, ok = Escalate(TierFast, TierStrong)
	if !ok || next != TierStrong {
		t.Fatalf("requested higher: %v %v", next, ok)
	}
	if _, ok := Escalate(TierStrong, TierStrong); ok {
		t.Fatal("strongest tier cannot escalate")
	}
}
