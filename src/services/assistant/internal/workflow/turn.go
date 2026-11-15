package workflow

import (
	"strings"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

const (
	statusSucceeded = "succeeded"
	statusFailed    = "failed"
	outOfScopeReply = "That is outside what this assistant can do. Ask about your training, sessions, templates, goals, supplements or biometrics."
	forbiddenReply  = "You no longer have access to this Athlete."
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
	finish := func(output TurnOutput, used []string) (any, error) {
		deliver := activities.DeliverInput{
			TurnID: input.TurnID, ConversationID: input.ConversationID, Athlete: input.Athlete, Request: lastUserMessage(input.Messages),
			Status: output.Status, Reply: output.Reply, Error: output.Error, UsedOperations: used,
		}
		if _, err := call[struct{}](ctx, activities.NameDeliver, deliver, quickRetry); err != nil {
			return nil, err
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
	decision, err := call[activities.Decision](ctx, activities.NameDecide, activities.DecideInput{Message: message, RequestedSurface: input.Surface}, quickRetry)
	if err != nil {
		decision = activities.Decision{Surface: tools.SurfaceGeneral, Fallback: true}
	}
	if decision.Surface == "out_of_scope" {
		return finish(TurnOutput{Status: statusSucceeded, Reply: outOfScopeReply}, nil)
	}
	surfaceName := input.Surface
	if surfaceName == "" {
		surfaceName = decision.Surface
	}
	surface, ok := tools.LookupSurface(surfaceName)
	if !ok {
		surface = tools.General()
	}
	retrieved, err := call[activities.RetrieveOutput](ctx, activities.NameRetrieve, activities.RetrieveInput{Identity: resolved.Identity, Query: message}, quickRetry)
	var snippets []store.Snippet
	if err == nil {
		snippets = retrieved.Snippets
	}
	result, err := w.runAgent(ctx, run{
		Surface: surface, Model: w.modelFor(surface.Name, true), Identity: resolved.Identity, ConversationID: input.ConversationID, Context: input.Context,
		Messages: input.Messages, Snippets: snippets,
		ForceDestructive: decision.DestructiveIntent || decision.UnrelatedHistorical, UnrelatedHistorical: decision.UnrelatedHistorical, DestructiveIntent: decision.DestructiveIntent,
	})
	if err != nil {
		return finish(TurnOutput{Status: statusFailed, Error: "assistant failed: " + err.Error(), Proposals: result.Proposals}, result.Used)
	}
	return finish(TurnOutput{Status: statusSucceeded, Reply: result.Reply, Proposals: result.Proposals}, result.Used)
}

func (w *Workflows) modelFor(surface string, coordinator bool) string {
	if coordinator {
		return w.Config.CoordinatorModel
	}
	if model := w.Config.SubagentModels[surface]; model != "" {
		return model
	}
	return w.Config.CoordinatorModel
}

func (w *Workflows) SubagentTask(ctx *workflow.WorkflowContext) (any, error) {
	var input SubagentInput
	if err := ctx.GetInput(&input); err != nil {
		return nil, err
	}
	surface, ok := tools.LookupSurface(input.Kind)
	if !ok || input.Kind == tools.SurfaceGeneral {
		return SubagentOutput{Error: "unknown subagent kind"}, nil
	}
	result, err := w.runAgent(ctx, run{
		Surface: surface, Model: w.modelFor(surface.Name, false), Identity: input.Identity, ConversationID: input.ConversationID, Depth: input.Depth,
		Context: input.Context, Task: input.Task, Messages: []llm.Message{{Role: "user", Content: input.Task}},
		ForceDestructive: input.ForceDestructive, UnrelatedHistorical: input.UnrelatedHistorical, DestructiveIntent: input.DestructiveIntent,
	})
	if err != nil {
		return SubagentOutput{UsedOperations: result.Used, Proposals: result.Proposals, Error: err.Error()}, nil
	}
	return SubagentOutput{Reply: result.Reply, UsedOperations: result.Used, Proposals: result.Proposals}, nil
}
