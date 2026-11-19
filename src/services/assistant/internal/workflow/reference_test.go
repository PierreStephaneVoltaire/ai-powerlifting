package workflow

import (
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
	"strings"
	"testing"
)

func TestReferenceIntentAndWeb(t *testing.T) {
	plan, ok := parseReferencePlan(`{"kind":"federations","federation_id":"IPF","query":"Are wrist wraps allowed?"}`, "under IPF rules?", RequestContext{})
	if !ok || plan.FederationID != "ipf" || plan.EffectiveDate != "" {
		t.Fatalf("plan: %+v", plan)
	}
	plan, ok = parseReferencePlan(`{"kind":"supplements","query":"Is ashwagandha useful?","no_web":true}`, "what about that?", RequestContext{})
	if !ok || plan.Kind != "supplements" || !plan.NoWeb {
		t.Fatalf("plan: %+v", plan)
	}
	for _, test := range []struct {
		ref  activities.ReferenceLookupOutput
		want bool
	}{
		{activities.ReferenceLookupOutput{Coverage: "full"}, false},
		{activities.ReferenceLookupOutput{Coverage: "partial", Gap: "interaction evidence"}, true},
		{activities.ReferenceLookupOutput{Coverage: "none", NoWeb: true}, false},
		{activities.ReferenceLookupOutput{Coverage: "partial"}, false},
	} {
		if got := useWeb(true, "", test.ref); got != test.want {
			t.Fatalf("web %v: %v", test.ref, got)
		}
	}
}

func TestReferenceIntentUsesRecentHistory(t *testing.T) {
	history := []llm.Message{{Role: "user", Content: "Tell me about ashwagandha"}, {Role: "assistant", Content: "What would you like to know?"}}
	messages := referenceIntentMessages(history, "What about interactions? Don't browse.", "general")
	if len(messages) != 4 || messages[1].Content != history[0].Content || messages[3].Content != "What about interactions? Don't browse." {
		t.Fatalf("history omitted: %+v", messages)
	}
}

func TestReferenceTaskScopeAndGap(t *testing.T) {
	full := activities.ReferenceLookupOutput{Scope: "supplements", Coverage: "full"}
	plan := referencePlan{Kind: "supplements", Query: "creatine"}
	if !sameReferenceTask(full, "creatine", "", plan, "creatine") || useWeb(true, "", full) {
		t.Fatal("full hit must suppress web")
	}
	if sameReferenceTask(full, "creatine", "", referencePlan{Kind: "supplements", Query: "ashwagandha"}, "ashwagandha") {
		t.Fatal("different compound requires lookup")
	}
	partial := activities.ReferenceLookupOutput{Scope: "supplements", Coverage: "partial", Gap: "interaction with medication"}
	if !sameReferenceTask(partial, "creatine", "", plan, partial.Gap) {
		t.Fatal("preserve existing gap")
	}
	rules := activities.ReferenceLookupOutput{Scope: "federation:ipf", Coverage: "full"}
	if sameReferenceTask(rules, "wraps", "", referencePlan{Kind: "federations", FederationID: "usapl", Query: "wraps"}, "wraps") {
		t.Fatal("different federation requires lookup")
	}
}

func TestReferenceMissWebTaskDoesNotContainHistory(t *testing.T) {
	history := []llm.Message{{Role: "user", Content: "private-history-marker: Is creatine useful?"}}
	messages := referenceIntentMessages(history, "Research its effects", "supplements")
	if len(messages) != 3 {
		t.Fatal("missing context")
	}
	plan, ok := parseReferencePlan(`{"kind":"supplements","query":"What are creatine's effects?"}`, "Research its effects", RequestContext{})
	if !ok {
		t.Fatal("invalid plan")
	}
	reference := activities.ReferenceLookupOutput{Scope: "supplements", Coverage: "none", Gap: plan.Query}
	task := reference.Gap
	webPrompt := webGapMessages(task)
	for _, message := range webPrompt {
		if strings.Contains(message.Content, "private-history-marker") {
			t.Fatalf("history leaked: %+v", webPrompt)
		}
	}
}
