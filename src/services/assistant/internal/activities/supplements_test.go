package activities

import (
	"context"
	"testing"

	"powerlifting/assistant/internal/agent"
)

func TestSupplementProposalsRequireCompoundAmountsInsteadOfCapsules(t *testing.T) {
	for _, dose := range []string{"2 pills/day", "3 caps/day", "4 capsules daily", "2 softgels", "2caps/day", "2 TABLETS"} {
		args := map[string]any{"phases": []any{map[string]any{"items": []any{map[string]any{"name": "Multivitamin", "dose": dose, "notes": "Vitamin C: 100 mg"}}}}}
		proposal, err := (&Deps{}).Propose(context.Background(), ProposeInput{
			Subject: Subject{Scope: []string{"supplement_phases_update", "health_get_supplements"}},
			Request: agent.ProposalRequest{Operation: "supplement_phases_update", ReadOperation: "health_get_supplements", Arguments: args},
		})
		if err != nil || proposal.Error == "" {
			t.Errorf("accepted capsule-only dose %q with ingredients buried in notes: %v, %v", dose, proposal, err)
		}
	}
	args := map[string]any{"phases": []any{map[string]any{"items": []any{map[string]any{
		"name": "Vitamin C", "dose": "300 mg/day", "notes": "100 mg from 2 multivitamin capsules + 200 mg standalone",
	}}}}}
	if reason := validateSupplementCompounds(args); reason != "" {
		t.Fatal(reason)
	}
}
