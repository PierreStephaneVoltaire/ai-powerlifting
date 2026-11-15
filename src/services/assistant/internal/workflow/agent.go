package workflow

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/config"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

const (
	approvalExpiredText = "The proposal expired without a decision."
	budgetText          = "I could not finish within my step limit. Ask again with a narrower request."
)

type Workflows struct {
	Config config.Config
}

var (
	quickRetry = &workflow.RetryPolicy{MaxAttempts: 3, InitialRetryInterval: 2 * time.Second, BackoffCoefficient: 2, MaxRetryInterval: 20 * time.Second}
	modelRetry = &workflow.RetryPolicy{MaxAttempts: 4, InitialRetryInterval: 5 * time.Second, BackoffCoefficient: 2, MaxRetryInterval: time.Minute}
)

func call[O any](ctx *workflow.WorkflowContext, name string, input any, policy *workflow.RetryPolicy) (O, error) {
	var output O
	err := ctx.CallActivity(name, workflow.WithActivityInput(input), workflow.WithActivityRetryPolicy(policy)).Await(&output)
	return output, err
}

func (w *Workflows) Register(registry *workflow.Registry) error {
	if err := registry.AddWorkflowN(NameConversationTurn, w.ConversationTurn); err != nil {
		return err
	}
	return registry.AddWorkflowN(NameSubagentTask, w.SubagentTask)
}

type run struct {
	Surface             tools.Surface
	Model               string
	Identity            access.Identity
	ConversationID      string
	Depth               int
	Context             RequestContext
	Task                string
	Messages            []llm.Message
	Snippets            []store.Snippet
	ForceDestructive    bool
	UnrelatedHistorical bool
	DestructiveIntent   bool
}

type outcome struct {
	Reply     string
	Used      []string
	Proposals []string
}

func (w *Workflows) runAgent(ctx *workflow.WorkflowContext, params run) (outcome, error) {
	var result outcome
	minted, err := call[activities.MintOutput](ctx, activities.NameMintToken, activities.MintInput{
		Identity: params.Identity, Surface: params.Surface.Name, ConversationID: params.ConversationID, WorkflowID: ctx.ID(),
	}, quickRetry)
	if err != nil {
		return result, err
	}
	subject := minted.Subject
	if len(subject.Scope) == 0 {
		result.Reply = "You do not have permission to use this assistant surface for this Athlete."
		return result, nil
	}
	listed, err := call[activities.ListToolsOutput](ctx, activities.NameListTools, activities.ListToolsInput{Subject: subject}, quickRetry)
	if err != nil {
		return result, err
	}
	defs := append(agent.ToolDefs(listed.Tools, params.Surface, subject.Scope), agent.PseudoTools(params.Surface, params.Depth, w.Config.MaxDepth)...)
	state := agent.State{Messages: append([]llm.Message{{Role: "system", Content: agent.SystemPrompt(agent.PromptContext{
		Surface: params.Surface.Name, SessionDate: params.Context.SessionDate, SessionIndex: params.Context.SessionIndex, ExerciseIndex: params.Context.ExerciseIndex,
		TemplateSK: params.Context.TemplateSK, Task: params.Task, UnrelatedHistorical: params.UnrelatedHistorical, DestructiveIntent: params.DestructiveIntent, Snippets: params.Snippets,
	})}}, params.Messages...)}
	limits := agent.Limits{MaxSteps: w.Config.MaxSteps, MaxTokens: w.Config.MaxTokens}
	sequence := 0
	for {
		if err := state.Exhausted(limits); err != nil {
			result.Reply = lastAssistantText(state.Messages, budgetText)
			return result, nil
		}
		response, err := call[llm.ChatResponse](ctx, activities.NameModelCall, activities.ModelCallInput{Model: params.Model, Messages: state.Messages, Tools: defs}, modelRetry)
		if err != nil {
			return result, err
		}
		state.Record(response)
		if len(response.ToolCalls) == 0 {
			result.Reply = response.Content
			return result, nil
		}
		for _, raw := range response.ToolCalls {
			sequence++
			text := w.dispatch(ctx, params, subject, agent.Classify(raw), sequence, &result)
			state.AddToolResult(raw.ID, text)
		}
	}
}

func lastAssistantText(messages []llm.Message, fallback string) string {
	for index := len(messages) - 1; index >= 0; index-- {
		if messages[index].Role == "assistant" && messages[index].Content != "" {
			return messages[index].Content
		}
	}
	return fallback
}

func (w *Workflows) dispatch(ctx *workflow.WorkflowContext, params run, subject activities.Subject, call agent.Call, sequence int, result *outcome) string {
	if call.Malformed != "" {
		return "error: " + call.Malformed
	}
	switch call.Kind {
	case agent.KindDelegate:
		return w.delegate(ctx, params, call, sequence, result)
	case agent.KindPropose:
		return w.propose(ctx, params, subject, call, sequence, result)
	}
	output, err := callActivity[activities.ToolCallOutput](ctx, activities.NameToolCall, activities.ToolCallInput{Subject: subject, Name: call.Name, Arguments: call.Arguments}, quickRetry)
	if err != nil {
		return "error: tool call failed: " + err.Error()
	}
	if !output.Denied && !output.IsError {
		result.Used = append(result.Used, call.Name)
	}
	return output.Text
}

func callActivity[O any](ctx *workflow.WorkflowContext, name string, input any, policy *workflow.RetryPolicy) (O, error) {
	return call[O](ctx, name, input, policy)
}

func (w *Workflows) delegate(ctx *workflow.WorkflowContext, params run, call agent.Call, sequence int, result *outcome) string {
	delegation, err := agent.ParseDelegation(call.Arguments)
	if err != nil {
		return "error: " + err.Error()
	}
	if params.Depth >= w.Config.MaxDepth {
		return "error: subagent depth limit reached"
	}
	if _, known := tools.LookupSurface(delegation.Kind); !known || delegation.Kind == tools.SurfaceGeneral || !params.Surface.CanDelegate(delegation.Kind) {
		return "error: this surface cannot delegate to " + delegation.Kind
	}
	var output SubagentOutput
	err = ctx.CallChildWorkflow(NameSubagentTask,
		workflow.WithChildWorkflowInstanceID(fmt.Sprintf("%s:sub:%d", ctx.ID(), sequence)),
		workflow.WithChildWorkflowInput(SubagentInput{
			Kind: delegation.Kind, Task: delegation.Task, Identity: params.Identity, ConversationID: params.ConversationID, Depth: params.Depth + 1, Context: params.Context,
			ForceDestructive: params.ForceDestructive, UnrelatedHistorical: params.UnrelatedHistorical, DestructiveIntent: params.DestructiveIntent,
		}),
	).Await(&output)
	if err != nil {
		return "error: subagent failed: " + err.Error()
	}
	result.Used = append(result.Used, output.UsedOperations...)
	result.Proposals = append(result.Proposals, output.Proposals...)
	if output.Error != "" {
		return "error: " + output.Error
	}
	return output.Reply
}

func (w *Workflows) propose(ctx *workflow.WorkflowContext, params run, subject activities.Subject, call agent.Call, sequence int, result *outcome) string {
	request, err := agent.ParseProposal(call.Arguments)
	if err != nil {
		return "error: " + err.Error()
	}
	id := fmt.Sprintf("%s:p:%d", ctx.ID(), sequence)
	view, err := callActivity[activities.ProposalView](ctx, activities.NamePropose, activities.ProposeInput{
		ID: id, TurnID: turnIDOf(ctx.ID()), Subject: subject, Request: request, ForceDestructive: params.ForceDestructive,
	}, quickRetry)
	if err != nil {
		return "error: proposal failed: " + err.Error()
	}
	if view.Error != "" {
		return "error: " + view.Error
	}
	result.Proposals = append(result.Proposals, id)
	var event activities.ApprovalEvent
	waitErr := ctx.WaitForExternalEvent(activities.ApprovalEventName(id), w.Config.ApprovalTimeout).Await(&event)
	switch {
	case errors.Is(waitErr, workflow.ErrTaskCanceled):
		_, _ = callActivity[activities.ProposalView](ctx, activities.NameExpireProposal, activities.ExpireInput{ID: id}, quickRetry)
		return approvalExpiredText
	case waitErr != nil:
		return "error: approval wait failed: " + waitErr.Error()
	case !event.Approve:
		return "The Person rejected this proposal. Nothing was changed."
	}
	committed, err := callActivity[activities.CommitOutput](ctx, activities.NameCommit, activities.CommitInput{ProposalID: id}, quickRetry)
	if err != nil {
		return "error: commit failed: " + err.Error()
	}
	if committed.Outcome == "committed" {
		result.Used = append(result.Used, request.Operation)
	}
	encoded, _ := json.Marshal(committed)
	return string(encoded)
}
