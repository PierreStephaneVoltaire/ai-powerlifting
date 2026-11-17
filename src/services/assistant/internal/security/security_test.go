package security

import (
	"slices"
	"testing"
)

func TestTriggerSet(t *testing.T) {
	cases := []struct {
		name  string
		input TriggerInput
		want  []string
	}{
		{"benign", TriggerInput{Signals: []string{SignalDestructive}}, nil},
		{"other person", TriggerInput{Signals: []string{SignalOtherPerson}}, []string{TriggerGuardSignal}},
		{"approval bypass", TriggerInput{Signals: []string{SignalApprovalBypass}}, []string{TriggerGuardSignal}},
		{"bulk delete", TriggerInput{Signals: []string{SignalBulkChange, SignalDestructive}}, []string{TriggerGuardSignal}},
		{"bulk alone", TriggerInput{Signals: []string{SignalBulkChange}}, nil},
		{"flagged", TriggerInput{Flagged: true}, []string{TriggerOrchestratorFlag}},
		{"destructive proposal", TriggerInput{Mutation: true, DestructiveChange: true}, []string{TriggerDestructive}},
		{"destructive read", TriggerInput{DestructiveChange: true}, nil},
		{"history gap mutation", TriggerInput{Mutation: true, HistoryGap: true}, []string{TriggerHistoryGap}},
		{"history gap without mutation", TriggerInput{HistoryGap: true}, nil},
	}
	for _, test := range cases {
		got := Triggers(test.input)
		if !slices.Equal(got, test.want) {
			t.Errorf("%s: got %v want %v", test.name, got, test.want)
		}
	}
}

func TestAssessmentCanOnlyTighten(t *testing.T) {
	if Tighten(RequireApproval, Allow) != RequireApproval || Tighten(Block, Allow) != Block || Tighten(Allow, Block) != Block || Tighten(Allow, RequireApproval) != RequireApproval {
		t.Fatal("tighten must never lower a verdict")
	}
	parsed := Parse(`{"verdict":"allow","risk":"low","reasons":["fine"]}`, []string{TriggerDestructive})
	if parsed.Verdict != RequireApproval {
		t.Fatalf("destructive floor was lowered: %v", parsed.Verdict)
	}
	if Parse(`{"verdict":"allow","risk":"low","reasons":[]}`, []string{TriggerGuardSignal}).Verdict != Allow {
		t.Fatal("allow with no floor must stay allow")
	}
	if Parse(`{"verdict":"block","risk":"high","reasons":["x"]}`, nil).Verdict != Block {
		t.Fatal("block lost")
	}
}

func TestMalformedAssessmentFailsTowardApproval(t *testing.T) {
	for _, content := range []string{"nope", `{"verdict":"grant","risk":"low","reasons":[]}`} {
		if got := Parse(content, nil); got.Verdict != RequireApproval || got.Source != "fallback" {
			t.Errorf("%q: %+v", content, got)
		}
	}
}
