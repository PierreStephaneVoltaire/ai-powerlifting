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
	"powerlifting/assistant/internal/visibility"
)

const (
	approvalExpiredText = "The proposal expired without a decision."
	budgetText          = "I could not finish within my step limit. No final answer was produced. Please retry with a narrower request."
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

const childBudgetShare = 2

type delegationRecord struct {
	Tier orchestration.Tier
}

type runState struct {
	Floor          security.Verdict
	Assessment     *security.Assessment
	Delegations    map[int]delegationRecord
	Budget         int
	Reference      activities.ReferenceLookupOutput
	ReferenceQuery string
	ReferenceDate  string
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
	WebOnly          bool
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
	HistoryBefore    string
	HistoryReference bool
	Reference        activities.ReferenceLookupOutput
	SharedWith       string
	State            *runState
}

type outcome struct {
	Reply         string
	Used          []string
	Proposals     []string
	Blocked       bool
	CommitFailure string
	Permissions   []string
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
	if ctx.IsPatched("reference-gap-isolated") && params.WebOnly {
		response, err := call[activities.ModelCallOutput](ctx, activities.NameModelCall, activities.ModelCallInput{
			Model: params.Model, Messages: webGapMessages(params.Task),
		}, modelRetry)
		if err != nil {
			return result, err
		}
		if response.Limit != "" {
			return result, errors.New(response.Limit)
		}
		result.Reply = response.Content
		return result, nil
	}
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
	if ctx.IsPatched("supplement-reference-before-draft") && params.Profile.Name == tools.SurfaceSupplements && params.State.Reference.Scope == "" {
		query := params.Message
		if params.Task != "" {
			query = params.Task
		}
		var recent []string
		for _, message := range params.Messages {
			if message.Role == "user" && message.Content != query {
				recent = append(recent, message.Content)
			}
		}
		w.lookupReference(ctx, params, map[string]any{"kind": "supplements", "query": query, "context": strings.Join(recent, "\n")})
		params.State.ReferenceQuery = params.Message
		if params.Task != "" {
			params.State.ReferenceQuery = params.Task
		}
		params.Reference = params.State.Reference
	}
	defs := append(agent.ToolDefs(listed.Tools, subject.Scope), agent.PseudoTools(subject.Scope, params.Depth, w.Config.MaxDepth)...)
	if params.WebOnly {
		defs = nil
	}
	state := agent.State{Messages: append([]llm.Message{{Role: "system", Content: agent.SystemPrompt(agent.PromptContext{
		Orchestrator: params.Orchestrator, Profile: params.Profile, SessionDate: params.Context.SessionDate, SessionIndex: params.Context.SessionIndex, ExerciseIndex: params.Context.ExerciseIndex,
		TemplateSK: params.Context.TemplateSK, Area: params.Context.Area, Task: params.Task, Signals: params.Signals, HistoryGap: params.HistoryGap, HistoryBefore: params.HistoryBefore, SharedWith: params.SharedWith, Assessment: params.State.Assessment, Snippets: params.Snippets, Reference: params.Reference,
	})}}, params.Messages...)}
	limits := agent.Limits{MaxSteps: w.Config.MaxSteps}
	meta := llm.Metadata{UserID: params.Identity.Person, ConversationID: params.ConversationID, WorkflowID: ctx.ID(), TurnID: turnIDOf(ctx.ID()), Role: params.role()}
	sequence := 0
	for {
		if err := state.Exhausted(limits); err != nil {
			result.Reply = withCommitFailure(lastAssistantText(state.Messages, budgetText), result.CommitFailure)
			return result, nil
		}
		stronger := w.Config.StrongModel
		if !params.WebOnly && stronger == w.Config.WebModel {
			stronger = ""
		}
		response, err := modelWithLimitRetry(params.Model, stronger, func(model string, retry bool) (activities.ModelCallOutput, error) {
			policy := modelRetry
			if retry {
				policy = &workflow.RetryPolicy{MaxAttempts: 1}
				params.Model = model
			}
			return call[activities.ModelCallOutput](ctx, activities.NameModelCall, activities.ModelCallInput{Model: model, Meta: meta, Messages: state.Messages, Tools: defs}, policy)
		})
		if err != nil {
			return result, err
		}
		state.Record(response)
		if len(response.ToolCalls) == 0 {
			result.Reply = response.Content
			if strings.TrimSpace(result.Reply) == "" {
				result.Reply = withCommitFailure("", result.CommitFailure)
			}
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

func withCommitFailure(reply, failure string) string {
	if failure == "" {
		return reply
	}
	notice := "The change was approved, but the write failed and nothing was changed: " + failure
	if strings.TrimSpace(reply) == "" {
		return notice
	}
	return reply + "\n\n" + notice
}

func lastAssistantText(messages []llm.Message, fallback string) string {
	for index := len(messages) - 1; index >= 0; index-- {
		if messages[index].Role == "user" {
			break
		}
		if messages[index].Role == "assistant" && messages[index].Content != "" {
			return messages[index].Content + "\n\n" + fallback
		}
	}
	return fallback
}

func (w *Workflows) dispatch(ctx *workflow.WorkflowContext, params run, subject activities.Subject, call agent.Call, sequence int, result *outcome) (string, bool) {
	if params.WebOnly {
		return "error: tools are unavailable during web research", false
	}
	if call.Malformed != "" {
		return "error: " + call.Malformed, false
	}
	switch call.Kind {
	case agent.KindReference:
		return w.lookupReference(ctx, params, call.Arguments), false
	case agent.KindHistory:
		return w.readHistory(ctx, params, call, result), false
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
	if params.State.Budget <= 0 {
		return "error: no delegation budget remains. Answer with what you have or tell the Person what could not be done."
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
	needsWeb := delegation.NeedsWeb
	if ctx.IsPatched("reference-lookup-before-web") {
		if ctx.IsPatched("reference-web-intent-v2") && needsWeb {
			intent, intentErr := callActivity[activities.ModelCallOutput](ctx, activities.NameModelCall, activities.ModelCallInput{
				Model: w.Config.CoordinatorModel, Messages: referenceIntentMessages(params.Messages, params.Message+"\nDelegated task: "+delegation.Task, params.Profile.Name), MaxTokens: 400,
			}, modelRetry)
			plan, valid := parseReferencePlan(intent.Content, delegation.Task, params.Context)
			if intentErr != nil || intent.Limit != "" || !valid {
				return "error: unable to determine whether reference lookup or browsing is appropriate"
			}
			params.State.Reference.NoWeb = params.State.Reference.NoWeb || plan.NoWeb
			if params.State.Reference.Coverage == "none" && plan.Kind != "none" {
				params.State.Reference.Gap = plan.Query
			}
			if plan.Kind == "none" && params.State.Reference.Scope != "" && !strings.EqualFold(strings.TrimSpace(delegation.Task), strings.TrimSpace(params.State.Reference.Gap)) && !strings.EqualFold(strings.TrimSpace(delegation.Task), strings.TrimSpace(params.State.ReferenceQuery)) {
				params.State.Reference = activities.ReferenceLookupOutput{NoWeb: params.State.Reference.NoWeb}
				params.State.ReferenceQuery = ""
			}
			if plan.Kind != "none" && !sameReferenceTask(params.State.Reference, params.State.ReferenceQuery, params.State.ReferenceDate, plan, delegation.Task) {
				args := map[string]any{"kind": plan.Kind, "query": plan.Query, "federation_id": plan.FederationID, "effective_date": plan.EffectiveDate}
				if text := w.lookupReference(ctx, params, args); params.State.Reference.Scope == "" {
					return text
				}
			}
		}
		params.Reference = params.State.Reference
		needsWeb = useWeb(needsWeb, params.Message, params.Reference)
		if needsWeb && params.Reference.Scope != "" && params.Reference.Gap != "" {
			delegation.Task = params.Reference.Gap
		}
	}
	usedWeb := needsWeb && w.Config.WebModel != ""
	if usedWeb {
		model = w.Config.WebModel
	} else if w.Config.WebModel != "" && model == w.Config.WebModel {
		return "error: web model cannot be used for a non-web task"
	}
	w.record(ctx, params.Identity.Person, params.ConversationID, eventKind, model, "started", map[string]any{
		"delegation_id": sequence, "kind": kind, "tier": tier.String(), "complexity": delegation.Complexity, "escalate_from": delegation.EscalateFrom, "needs_web": delegation.NeedsWeb, "web": usedWeb, "model": model, "depth": params.Depth + 1,
	})
	params.State.Delegations[sequence] = delegationRecord{Tier: tier}
	params.State.Budget--
	share := min(childBudgetShare, params.State.Budget)
	params.State.Budget -= share
	childMessage := params.Message
	childReference := params.Reference
	childContext := params.Context
	childSignals := params.Signals
	childAssessment := params.State.Assessment
	gapOnly := usedWeb && params.Reference.Scope != ""
	if gapOnly {
		childMessage = delegation.Task
		childReference = activities.ReferenceLookupOutput{NoWeb: params.Reference.NoWeb}
		childContext = RequestContext{}
		childSignals = nil
		childAssessment = nil
	}
	var output SubagentOutput
	err = ctx.CallChildWorkflow(NameSubagentTask,
		workflow.WithChildWorkflowInstanceID(fmt.Sprintf("%s:sub:%d", ctx.ID(), sequence)),
		workflow.WithChildWorkflowInput(SubagentInput{
			WebOnly: gapOnly, Kind: kind, Model: model, Task: delegation.Task, Message: childMessage, Identity: params.Identity, ConversationID: params.ConversationID, Depth: params.Depth + 1, Budget: share, Context: childContext,
			Signals: childSignals, HistoryGap: params.HistoryGap, HistoryReference: params.HistoryReference, Floor: params.State.Floor, Assessment: childAssessment, Reference: childReference,
		}),
	).Await(&output)
	if err != nil {
		output = SubagentOutput{Error: "subagent failed: " + err.Error()}
	} else {
		params.State.Budget += max(0, min(output.Budget, share))
	}
	result.Used = append(result.Used, output.UsedOperations...)
	result.Permissions = visibility.Union(result.Permissions, output.Permissions)
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
		result.CommitFailure = ""
	} else {
		result.CommitFailure = committed.Text
	}
	encoded, _ := json.Marshal(committed)
	return string(encoded)
}
