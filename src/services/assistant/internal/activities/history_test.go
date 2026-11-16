package activities

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/store"
)

func TestRetryRetainsInstructionsFromPendingAndStoppedTurns(t *testing.T) {
	for _, status := range []string{"queued", "running", "cancelled"} {
		messages := historyMessages(store.HistoryTurn{
			Status:  status,
			Request: json.RawMessage(`{"messages":[{"role":"user","content":"Create the current block phase using verified label data. Do not do any new web research."}]}`),
		}, historyLatestCap)
		if len(messages) != 2 || !strings.Contains(messages[0].Content, "Do not do any new web research") || messages[1].Content == "" {
			t.Fatalf("retry lost the original instructions for %s: %v", status, messages)
		}
	}
}

func TestRetryRecoversProposalIngredientsOnlyWithPermission(t *testing.T) {
	s, ref := assistantTestStore(t)
	ctx := context.Background()
	if err := s.InsertTurn(ctx, store.Turn{ID: "earlier", ConversationID: ref.ID, PersonPK: "p", WorkflowID: "earlier", Status: "running", Request: json.RawMessage(`{"messages":[{"role":"user","content":"Use the verified ingredients without new web research."}]}`)}); err != nil {
		t.Fatal(err)
	}
	if err := s.InsertProposal(ctx, store.Proposal{
		ID: "proposal", TurnID: "earlier", ConversationID: ref.ID, Operation: "supplement_phases_update",
		Arguments: json.RawMessage(`{"phases":[{"items":[{"name":"Multi","dose":"2 capsules/day","notes":"Verified label contribution: 123 mg of compound A"}]}]}`),
		Diff:      json.RawMessage(`{}`), TargetRead: json.RawMessage(`{}`),
	}); err != nil {
		t.Fatal(err)
	}
	for _, permissions := range [][]string{{"program:read", "program:write"}, {"program:read"}} {
		history, err := (&Deps{Store: s}).History(ctx, HistoryInput{ConversationID: ref.ID, Identity: access.Identity{Athlete: "a", Person: "p", Permissions: permissions}})
		if err != nil || len(history.Messages) != 2 {
			t.Fatalf("history: %v, %v", history, err)
		}
		contains := strings.Contains(history.Messages[1].Content, "Verified label contribution: 123 mg")
		if contains != (len(permissions) == 2) {
			t.Fatalf("proposal context permission mismatch: %v", history)
		}
	}
}
