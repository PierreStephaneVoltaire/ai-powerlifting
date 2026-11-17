package activities

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
)

func TestHistoryPreservesCompleteMessages(t *testing.T) {
	content := strings.Repeat("compound findings\n", 2000) + "FINAL INGREDIENT"
	request, err := json.Marshal(map[string]any{"messages": []llm.Message{{Role: "user", Content: content}}})
	if err != nil {
		t.Fatal(err)
	}
	messages := historyMessages(store.HistoryTurn{Status: "succeeded", Request: request, Reply: content})
	if len(messages) != 2 || messages[0].Content != content || messages[1].Content != content {
		t.Fatal("history lost request or reply data")
	}
}

func TestHistoryIncludesFiveTurnsAndPagesOlderContext(t *testing.T) {
	s, ref := assistantTestStore(t)
	ctx := context.Background()
	content := strings.Repeat("complete ingredient data\n", 1500) + "FINAL INGREDIENT"
	for index := 1; index <= 7; index++ {
		id := fmt.Sprintf("turn-%d", index)
		request, err := json.Marshal(map[string]any{"messages": []llm.Message{{Role: "user", Content: id + content}}})
		if err != nil {
			t.Fatal(err)
		}
		if err := s.InsertTurn(ctx, store.Turn{ID: id, ConversationID: ref.ID, PersonPK: "p", WorkflowID: id, Status: "running", Request: request}); err != nil {
			t.Fatal(err)
		}
		if err := s.CompleteTurn(ctx, store.Completion{TurnID: id, Status: "succeeded", Reply: content}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := s.Pool.Exec(ctx, "UPDATE turns SET created_at = '2026-11-16T00:00:00Z'"); err != nil {
		t.Fatal(err)
	}
	deps := &Deps{Store: s}
	input := HistoryInput{ConversationID: ref.ID, Identity: access.Identity{Athlete: "a", Person: "p", Permissions: []string{"program:read"}}}
	recent, err := deps.History(ctx, input)
	if err != nil || recent.Turns != 5 || len(recent.Messages) != 10 || recent.NextBefore != "turn-3" {
		t.Fatalf("recent history: turns=%d messages=%d cursor=%q error=%v", recent.Turns, len(recent.Messages), recent.NextBefore, err)
	}
	for index := 0; index < 5; index++ {
		if recent.Messages[index*2].Content != fmt.Sprintf("turn-%d", index+3)+content || recent.Messages[index*2+1].Content != content {
			t.Fatal("recent turn was cut or reordered")
		}
	}
	input.TurnID = recent.NextBefore
	older, err := deps.History(ctx, input)
	if err != nil || older.Turns != 2 || older.NextBefore != "" || len(older.Messages) != 4 {
		t.Fatalf("older history: turns=%d messages=%d cursor=%q error=%v", older.Turns, len(older.Messages), older.NextBefore, err)
	}
	if older.Messages[0].Content != "turn-1"+content || older.Messages[2].Content != "turn-2"+content {
		t.Fatal("older history was cut or skipped")
	}
	input.Identity.Person = "someone-else"
	denied, err := deps.History(ctx, input)
	if err != nil || len(denied.Messages) != 0 {
		t.Fatal("history exposed another Person's conversation")
	}
}

func TestRetryRetainsInstructionsFromPendingAndStoppedTurns(t *testing.T) {
	for _, status := range []string{"queued", "running", "cancelled"} {
		messages := historyMessages(store.HistoryTurn{
			Status:  status,
			Request: json.RawMessage(`{"messages":[{"role":"user","content":"Create the current block phase using verified label data. Do not do any new web research."}]}`),
		})
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
