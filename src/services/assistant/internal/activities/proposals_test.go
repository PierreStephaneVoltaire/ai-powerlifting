package activities

import (
	"context"
	"strings"
	"testing"

	"powerlifting/assistant/internal/agent"
)

func TestTemplatePatchProposalRejectsPreviewsAndMismatchedTargets(t *testing.T) {
	deps := &Deps{}
	input := ProposeInput{
		Subject: Subject{Scope: []string{"template_get", "template_patch"}},
		Request: agent.ProposalRequest{
			Operation:     "template_patch",
			Arguments:     map[string]any{"sk": "template#1"},
			TargetID:      "template#1",
			ReadOperation: "template_get",
			ReadArguments: map[string]any{"sk": "template#2"},
		},
	}
	view, err := deps.Propose(context.Background(), input)
	if err != nil || !strings.Contains(view.Error, "apply=true") {
		t.Fatalf("expected the preview to be rejected, got %+v, %v", view, err)
	}
	input.Request.Arguments["apply"] = true
	view, err = deps.Propose(context.Background(), input)
	if err != nil || !strings.Contains(view.Error, "same template sk") {
		t.Fatalf("expected a mismatched target to be rejected, got %+v, %v", view, err)
	}
}
