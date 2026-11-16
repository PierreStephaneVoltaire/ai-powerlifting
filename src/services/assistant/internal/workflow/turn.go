package workflow

import (
	"slices"
	"strings"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/security"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/visibility"
)

const (
	statusSucceeded = "succeeded"
	statusFailed    = "failed"
	forbiddenReply  = "You no longer have access to this Athlete."
	blockedReply    = "I can't help with that request."
	historyNote     = "Note: earlier conversation history was unavailable, so I answered from this conversation only. Restate any details I may have missed."
)

func turnIDOf(workflowID string) string {
	if index := strings.Index(workflowID, ":"); index > 0 {
		return workflowID[:index]
	}
	return workflowID
}

func lastUserMessage(messages []llm.Message) string {
	for index := len(messages) - 1; index >= 0; index-- {
		if messages[index].Role == "user" {
			return messages[index].Content
		}
	}
	return ""
}

func (w *Workflows) ConversationTurn(ctx *workflow.WorkflowContext) (any, error) {
	var input TurnInput
	if err := ctx.GetInput(&input); err != nil {
		return nil, err
	}
	var extraPermissions []string
	finish := func(output TurnOutput, used []string) (any, error) {
		deliver := activities.DeliverInput{
			Person: input.Person, TurnID: input.TurnID, ConversationID: input.ConversationID, Athlete: input.Athlete, Request: lastUserMessage(input.Messages),
			Status: output.Status, Reply: output.Reply, Error: output.Error, UsedOperations: used, ExtraPermissions: extraPermissions,
		}
		delivered, err := call[activities.DeliverOutput](ctx, activities.NameDeliver, deliver, quickRetry)
		if err != nil {
			return nil, err
		}
		if output.Status == statusSucceeded {
			output.Reply = delivered.Reply
		}
		return output, nil
	}
	resolved, err := call[activities.ResolveOutput](ctx, activities.NameResolveIdentity, activities.ResolveInput{
		TurnID: input.TurnID, Person: input.Person, Athlete: input.Athlete, ConversationID: input.ConversationID, WorkflowID: ctx.ID(),
	}, quickRetry)
	if err != nil {
		return finish(TurnOutput{Status: statusFailed, Error: "identity could not be resolved: " + err.Error()}, nil)
	}
	if !resolved.Allowed {
		return finish(TurnOutput{Status: statusFailed, Reply: forbiddenReply, Error: resolved.Reason}, nil)
	}
	message := lastUserMessage(input.Messages)
	guard, err := call[activities.GuardOutput](ctx, activities.NameGuard, activities.GuardInput{Person: input.Person, Message: message}, quickRetry)
	if err != nil {
		return finish(TurnOutput{Status: statusFailed, Error: "guard failed: " + err.Error()}, nil)
	}
	if guard.Rejected {
		return finish(TurnOutput{Status: statusSucceeded, Reply: guard.Reply}, nil)
	}
	profile, ok := tools.LookupProfile(input.Surface)
	if !ok {
		profile, _ = tools.LookupProfile("")
	}
	state := newRunState()
	state.Budget = w.Config.DelegationBudget
	if security.GuardTriggers(guard.Signals) {
		assessment := w.assess(ctx, "pre", activities.SecurityReviewInput{
			Person: input.Person, ConversationID: input.ConversationID, WorkflowID: ctx.ID(),
			Triggers: security.Triggers(security.TriggerInput{Signals: guard.Signals}), Signals: guard.Signals, Message: message,
		})
		state.apply(assessment)
		if assessment.Verdict == security.Block {
			return finish(TurnOutput{Status: statusSucceeded, Reply: blockedReply}, nil)
		}
	}
	retrieved, retrieveErr := call[activities.RetrieveOutput](ctx, activities.NameRetrieve, activities.RetrieveInput{
		Identity: resolved.Identity, Query: message, ConversationID: input.ConversationID, WorkflowID: ctx.ID(),
	}, quickRetry)
	history, historyErr := call[activities.HistoryOutput](ctx, activities.NameHistory, activities.HistoryInput{
		Identity: resolved.Identity, ConversationID: input.ConversationID, TurnID: input.TurnID,
	}, quickRetry)
	var snippets []store.Snippet
	if retrieveErr == nil {
		for _, snippet := range retrieved.Snippets {
			if historyErr == nil && snippet.ConversationID == input.ConversationID && history.Turns > 0 {
				continue
			}
			snippets = append(snippets, snippet)
		}
	}
	historyLoaded := historyErr == nil && history.Turns > 0
	historyGap := historyErr != nil || (!historyLoaded && len(snippets) == 0 && guard.HistoryReference)
	for _, snippet := range snippets {
		extraPermissions = visibility.Union(extraPermissions, snippet.Permissions)
	}
	if historyErr == nil {
		extraPermissions = visibility.Union(extraPermissions, history.Permissions)
	}
	if historyGap {
		outcome := "empty"
		if historyErr != nil {
			outcome = "failed"
		}
		w.record(ctx, input.Person, input.ConversationID, "history_unavailable", "", outcome, map[string]any{"history_reference": guard.HistoryReference})
	}
	w.record(ctx, input.Person, input.ConversationID, "orchestrate", w.Config.CoordinatorModel, "start", map[string]any{
		"profile": profile.Name, "signals": guard.Signals, "history_gap": historyGap, "history_turns": history.Turns, "snippets": len(snippets), "security_floor": string(state.Floor),
	})
	sharedWith := ""
	if historyErr == nil && history.Shared {
		sharedWith = resolved.Identity.Person
	}
	result, err := w.runAgent(ctx, run{
		Profile: profile, Orchestrator: true, Model: w.Config.CoordinatorModel, Identity: resolved.Identity, ConversationID: input.ConversationID,
		Context: input.Context, Message: message, Messages: append(slices.Clone(history.Messages), input.Messages...), Snippets: snippets,
		Signals: guard.Signals, HistoryGap: historyGap, HistoryReference: guard.HistoryReference, SharedWith: sharedWith, State: state,
	})
	if err != nil {
		return finish(TurnOutput{Status: statusFailed, Error: "assistant failed: " + err.Error(), Proposals: result.Proposals}, result.Used)
	}
	reply := result.Reply
	if historyGap && guard.HistoryReference && !result.Blocked {
		reply = strings.TrimSpace(reply + "\n\n" + historyNote)
	}
	return finish(TurnOutput{Status: statusSucceeded, Reply: reply, Proposals: result.Proposals}, result.Used)
}

func (w *Workflows) SubagentTask(ctx *workflow.WorkflowContext) (any, error) {
	var input SubagentInput
	if err := ctx.GetInput(&input); err != nil {
		return nil, err
	}
	profile, ok := tools.LookupProfile(input.Kind)
	if !ok || !slices.Contains(tools.SubagentKinds(), input.Kind) {
		return SubagentOutput{Error: "unknown subagent kind"}, nil
	}
	state := newRunState()
	state.Budget = input.Budget
	state.Floor = input.Floor
	state.Assessment = input.Assessment
	result, err := w.runAgent(ctx, run{
		Profile: profile, Model: input.Model, Identity: input.Identity, ConversationID: input.ConversationID, Depth: input.Depth,
		Context: input.Context, Task: input.Task, Message: input.Message, Messages: []llm.Message{{Role: "user", Content: input.Task}},
		Signals: input.Signals, HistoryGap: input.HistoryGap, HistoryReference: input.HistoryReference, State: state,
	})
	if err != nil {
		return SubagentOutput{Budget: state.Budget, UsedOperations: result.Used, Proposals: result.Proposals, Floor: state.Floor, Error: err.Error()}, nil
	}
	return SubagentOutput{Budget: state.Budget, Reply: result.Reply, UsedOperations: result.Used, Proposals: result.Proposals, Floor: state.Floor}, nil
}

func (w *Workflows) SecurityAssessment(ctx *workflow.WorkflowContext) (any, error) {
	var input activities.SecurityReviewInput
	if err := ctx.GetInput(&input); err != nil {
		return nil, err
	}
	assessment, err := call[security.Assessment](ctx, activities.NameSecurityReview, input, quickRetry)
	if err != nil {
		return security.Fallback(input.Triggers, "assessment failed"), nil
	}
	return assessment, nil
}
