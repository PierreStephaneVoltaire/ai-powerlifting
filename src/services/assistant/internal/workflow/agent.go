package workflow

import (
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/config"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/orchestration"
	"powerlifting/assistant/internal/security"
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
	if err := registry.AddWorkflowN(NameSecurityAssessment, w.SecurityAssessment); err != nil {
		return err
	}
	return registry.AddWorkflowN(NameSubagentTask, w.SubagentTask)
}

func (w *Workflows) models() orchestration.Models {
	return orchestration.Models{Fast: w.Config.FastModel, Standard: w.Config.CoordinatorModel, Strong: w.Config.StrongModel}
}

type delegationRecord struct {
	Tier orchestration.Tier
}

type runState struct {
	Floor       security.Verdict
	Assessment  *security.Assessment
	Delegations map[int]delegationRecord
}

func newRunState() *runState {
	return &runState{Floor: security.Allow, Delegations: map[int]delegationRecord{}}
}

func (s *runState) apply(assessment security.Assessment) {
	s.Floor = security.Tighten(s.Floor, assessment.Verdict)
	copied := assessment
	s.Assessment = &copied
}

type run struct {
	Profile          tools.Profile
	Orchestrator     bool
	Model            string
	Identity         access.Identity
	ConversationID   string
	Depth            int
	Context          RequestContext
	Task             string
	Message          string
	Messages         []llm.Message
	Snippets         []store.Snippet
	Signals          []string
	HistoryGap       bool
	HistoryReference bool
	State            *runState
}

type outcome struct {
	Reply     string
	Used      []string
	Proposals []string
	Blocked   bool
}

func (p run) role() string {
	if p.Orchestrator {
		return "orchestrator"
	}
	return "subagent"
}

func (w *Workflows) record(ctx *workflow.WorkflowContext, person, conversationID, kind, model, outcome string, detail map[string]any) {
	_, _ = call[struct{}](ctx, activities.NameRecord, activities.RecordInput{
		Kind: kind, Person: person, ConversationID: conversationID, WorkflowID: ctx.ID(), Model: model, Outcome: outcome, Detail: detail,
	}, quickRetry)
}

func (w *Workflows) assess(ctx *workflow.WorkflowContext, suffix string, input activities.SecurityReviewInput) security.Assessment {
	var assessment security.Assessment
	err := ctx.CallChildWorkflow(NameSecurityAssessment,
		workflow.WithChildWorkflowInstanceID(fmt.Sprintf("%s:sec:%s", ctx.ID(), suffix)),
		workflow.WithChildWorkflowInput(input),
	).Await(&assessment)
	if err != nil || assessment.Verdict == "" {
		return security.Fallback(input.Triggers, "assessment unavailable")
	}
	return assessment
}

func (w *Workflows) runAgent(ctx *workflow.WorkflowContext, params run) (outcome, error) {
	var result outcome
	minted, err := call[activities.MintOutput](ctx, activities.NameMintToken, activities.MintInput{
		Identity: params.Identity, ConversationID: params.ConversationID, WorkflowID: ctx.ID(),
	}, quickRetry)
	if err != nil {
		return result, err
	}
	subject := minted.Subject
	if len(subject.Scope) == 0 {
		result.Reply = "You do not have permission to use this assistant for this Athlete."
		return result, nil
	}
	listed, err := call[activities.ListToolsOutput](ctx, activities.NameListTools, activities.ListToolsInput{Subject: subject}, quickRetry)
	if err != nil {
		return result, err
	}
	defs := append(agent.ToolDefs(listed.Tools, subject.Scope), agent.PseudoTools(subject.Scope, params.Depth, w.Config.MaxDepth)...)
	state := agent.State{Messages: append([]llm.Message{{Role: "system", Content: agent.SystemPrompt(agent.PromptContext{
		Orchestrator: params.Orchestrator, Profile: params.Profile, SessionDate: params.Context.SessionDate, SessionIndex: params.Context.SessionIndex, ExerciseIndex: params.Context.ExerciseIndex,
		TemplateSK: params.Context.TemplateSK, Task: params.Task, Signals: params.Signals, HistoryGap: params.HistoryGap, Assessment: params.State.Assessment, Snippets: params.Snippets,
	})}}, params.Messages...)}
	limits := agent.Limits{MaxSteps: w.Config.MaxSteps, MaxTokens: w.Config.MaxTokens}
	meta := llm.Metadata{UserID: params.Identity.Person, ConversationID: params.ConversationID, WorkflowID: ctx.ID(), TurnID: turnIDOf(ctx.ID()), Role: params.role()}
	sequence := 0
	for {
		if err := state.Exhausted(limits); err != nil {
			result.Reply = lastAssistantText(state.Messages, budgetText)
			return result, nil
		}
		response, err := call[llm.ChatResponse](ctx, activities.NameModelCall, activities.ModelCallInput{Model: params.Model, Meta: meta, Messages: state.Messages, Tools: defs}, modelRetry)
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
			text, stop := w.dispatch(ctx, params, subject, agent.Classify(raw), sequence, &result)
			if stop {
				result.Reply = text
				result.Blocked = true
				return result, nil
			}
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

func (w *Workflows) dispatch(ctx *workflow.WorkflowContext, params run, subject activities.Subject, call agent.Call, sequence int, result *outcome) (string, bool) {
	if call.Malformed != "" {
		return "error: " + call.Malformed, false
	}
	switch call.Kind {
	case agent.KindDelegate:
		return w.delegate(ctx, params, call, sequence, result), false
	case agent.KindReview:
		return w.review(ctx, params, call), false
	case agent.KindFlag:
		return w.flag(ctx, params, call, sequence)
	case agent.KindPropose:
		return w.propose(ctx, params, subject, call, sequence, result), false
	}
	output, err := callActivity[activities.ToolCallOutput](ctx, activities.NameToolCall, activities.ToolCallInput{Subject: subject, Name: call.Name, Arguments: call.Arguments}, quickRetry)
	if err != nil {
		return "error: tool call failed: " + err.Error(), false
	}
	if !output.Denied && !output.IsError {
		result.Used = append(result.Used, call.Name)
	}
	return output.Text, false
}

func callActivity[O any](ctx *workflow.WorkflowContext, name string, input any, policy *workflow.RetryPolicy) (O, error) {
	return call[O](ctx, name, input, policy)
}

func (w *Workflows) flag(ctx *workflow.WorkflowContext, params run, call agent.Call, sequence int) (string, bool) {
	reason, err := agent.ParseFlag(call.Arguments)
	if err != nil {
		return "error: " + err.Error(), false
	}
	assessment := w.assess(ctx, fmt.Sprintf("flag%d", sequence), activities.SecurityReviewInput{
		Person: params.Identity.Person, ConversationID: params.ConversationID, WorkflowID: ctx.ID(),
		Triggers: security.Triggers(security.TriggerInput{Flagged: true}), Signals: params.Signals, Message: params.Message, Reason: reason, HistoryGap: params.HistoryGap,
	})
	params.State.apply(assessment)
	if assessment.Verdict == security.Block {
		return blockedReply, true
	}
	return fmt.Sprintf("security assessment: %s (risk %s). %s. Proceed only within it; it never grants access.", assessment.Verdict, assessment.Risk, strings.Join(assessment.Reasons, "; ")), false
}

func (w *Workflows) review(ctx *workflow.WorkflowContext, params run, call agent.Call) string {
	review, err := agent.ParseReview(call.Arguments)
	if err != nil {
		return "error: " + err.Error()
	}
	record, known := params.State.Delegations[review.DelegationID]
	if !known {
		return "error: unknown delegation_id"
	}
	outcomeName := "passed"
	if !review.Passed {
		outcomeName = "failed"
	}
	w.record(ctx, params.Identity.Person, params.ConversationID, "review", w.models().Model(record.Tier), outcomeName, map[string]any{
		"delegation_id": review.DelegationID, "tier": record.Tier.String(), "reason": review.Reason, "source": "orchestrator",
	})
	if review.Passed {
		return "review recorded: passed"
	}
	return w.escalationAdvice(review.DelegationID, record.Tier)
}

func (w *Workflows) escalationAdvice(id int, tier orchestration.Tier) string {
	next, ok := orchestration.Escalate(tier, tier)
	if !ok || w.models().Model(next) == w.models().Model(tier) {
		return "review recorded: failed. No stronger model is available; tell the Person what could not be done."
	}
	return fmt.Sprintf("review recorded: failed. Call delegate_subagent again with escalate_from=%d to retry on the %s model.", id, next)
}

func (w *Workflows) delegate(ctx *workflow.WorkflowContext, params run, call agent.Call, sequence int, result *outcome) string {
	delegation, err := agent.ParseDelegation(call.Arguments)
	if err != nil {
		return "error: " + err.Error()
	}
	if params.Depth >= w.Config.MaxDepth {
		return "error: subagent depth limit reached"
	}
	kind := delegation.Kind
	if kind == "" {
		kind = params.Profile.DefaultDelegate
	}
	if !slices.Contains(tools.SubagentKinds(), kind) {
		return "error: unknown subagent kind " + kind
	}
	models := w.models()
	defaultModel := w.Config.SubagentModels[kind]
	if defaultModel == "" {
		defaultModel = w.Config.CoordinatorModel
	}
	tier := models.Resolve(delegation.Complexity, defaultModel)
	eventKind := "delegate"
	if delegation.EscalateFrom > 0 {
		previous, known := params.State.Delegations[delegation.EscalateFrom]
		if !known {
			return "error: unknown escalate_from delegation"
		}
		next, ok := orchestration.Escalate(previous.Tier, tier)
		if !ok || models.Model(next) == models.Model(previous.Tier) {
			return "error: no stronger model is available; tell the Person what could not be done"
		}
		tier = next
		eventKind = "escalate"
	}
	model := models.Model(tier)
	w.record(ctx, params.Identity.Person, params.ConversationID, eventKind, model, "started", map[string]any{
		"delegation_id": sequence, "kind": kind, "tier": tier.String(), "complexity": delegation.Complexity, "escalate_from": delegation.EscalateFrom, "depth": params.Depth + 1,
	})
	params.State.Delegations[sequence] = delegationRecord{Tier: tier}
	var output SubagentOutput
	err = ctx.CallChildWorkflow(NameSubagentTask,
		workflow.WithChildWorkflowInstanceID(fmt.Sprintf("%s:sub:%d", ctx.ID(), sequence)),
		workflow.WithChildWorkflowInput(SubagentInput{
			Kind: kind, Model: model, Task: delegation.Task, Message: params.Message, Identity: params.Identity, ConversationID: params.ConversationID, Depth: params.Depth + 1, Context: params.Context,
			Signals: params.Signals, HistoryGap: params.HistoryGap, HistoryReference: params.HistoryReference, Floor: params.State.Floor, Assessment: params.State.Assessment,
		}),
	).Await(&output)
	if err != nil {
		output = SubagentOutput{Error: "subagent failed: " + err.Error()}
	}
	result.Used = append(result.Used, output.UsedOperations...)
	result.Proposals = append(result.Proposals, output.Proposals...)
	params.State.Floor = security.Tighten(params.State.Floor, output.Floor)
	if output.Error != "" || strings.TrimSpace(output.Reply) == "" {
		reason := output.Error
		if reason == "" {
			reason = "empty result"
		}
		w.record(ctx, params.Identity.Person, params.ConversationID, "review", model, "failed", map[string]any{"delegation_id": sequence, "tier": tier.String(), "reason": reason, "source": "automatic"})
		return fmt.Sprintf("[delegation_id=%d tier=%s] error: %s. %s", sequence, tier, reason, w.escalationAdvice(sequence, tier))
	}
	return fmt.Sprintf("[delegation_id=%d tier=%s]\n%s", sequence, tier, output.Reply)
}

func (w *Workflows) propose(ctx *workflow.WorkflowContext, params run, subject activities.Subject, call agent.Call, sequence int, result *outcome) string {
	request, err := agent.ParseProposal(call.Arguments)
	if err != nil {
		return "error: " + err.Error()
	}
	if params.State.Floor == security.Block {
		return "error: blocked by the security assessment"
	}
	operation, known := tools.Lookup(request.Operation)
	destructive := known && operation.Destructive || request.DestructiveHint || slices.Contains(params.Signals, security.SignalDestructive)
	historyGap := params.HistoryGap && (request.HistoryDependent || params.HistoryReference)
	assessment := params.State.Assessment
	if known && operation.Mutating {
		triggers := security.Triggers(security.TriggerInput{Mutation: true, DestructiveChange: destructive, HistoryGap: historyGap})
		if len(triggers) > 0 {
			arguments, _ := json.Marshal(request.Arguments)
			reviewed := w.assess(ctx, fmt.Sprintf("p%d", sequence), activities.SecurityReviewInput{
				Person: params.Identity.Person, ConversationID: params.ConversationID, WorkflowID: ctx.ID(), Triggers: triggers, Signals: params.Signals,
				Message: params.Message, Operation: request.Operation, Summary: request.Summary, Arguments: string(arguments), HistoryGap: historyGap,
			})
			params.State.apply(reviewed)
			assessment = &reviewed
			if reviewed.Verdict == security.Block {
				return "error: blocked by the security assessment: " + strings.Join(reviewed.Reasons, "; ")
			}
		}
	}
	id := fmt.Sprintf("%s:p:%d", ctx.ID(), sequence)
	view, err := callActivity[activities.ProposalView](ctx, activities.NamePropose, activities.ProposeInput{
		ID: id, TurnID: turnIDOf(ctx.ID()), Subject: subject, Request: request,
		ForceDestructive: destructive || params.State.Floor == security.RequireApproval || historyGap, Assessment: assessment,
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
