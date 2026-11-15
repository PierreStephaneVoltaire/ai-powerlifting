package activities

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

const maxSnapshotBytes = 16 * 1024

type targetRead struct {
	Operation string         `json:"operation"`
	Arguments map[string]any `json:"arguments"`
}

func (d *Deps) Propose(ctx context.Context, in ProposeInput) (ProposalView, error) {
	reject := func(reason string) (ProposalView, error) {
		return ProposalView{ID: in.ID, Operation: in.Request.Operation, Error: reason}, nil
	}
	request := in.Request
	operation, known := tools.Lookup(request.Operation)
	switch {
	case !known || !operation.Mutating:
		return reject("operation is not a write operation")
	case !slices.Contains(in.Subject.Scope, request.Operation):
		return reject("operation is outside the allowed scope")
	case tools.IsMutating(request.ReadOperation) || !slices.Contains(in.Subject.Scope, request.ReadOperation):
		return reject("read_operation must be a permitted read operation")
	}
	read, err := d.ToolCall(ctx, ToolCallInput{Subject: in.Subject, Name: request.ReadOperation, Arguments: request.ReadArguments})
	if err != nil {
		return ProposalView{}, err
	}
	if read.IsError {
		return reject("target could not be read: " + agent.Truncate(read.Text, 300))
	}
	version := tools.Version(read.Text)
	var before any = json.RawMessage(nil)
	if len(read.Text) <= maxSnapshotBytes && json.Valid([]byte(read.Text)) {
		before = json.RawMessage(read.Text)
	} else {
		before = agent.Truncate(read.Text, 2000)
	}
	diff := mustJSON(map[string]any{"operation": request.Operation, "arguments": request.Arguments, "before": before, "target_version": version})
	proposal := store.Proposal{
		ID:             in.ID,
		TurnID:         in.TurnID,
		ConversationID: in.Subject.ConversationID,
		WorkflowID:     in.Subject.WorkflowID,
		AthletePK:      in.Subject.Athlete,
		RequesterPK:    in.Subject.Person,
		Operation:      request.Operation,
		Arguments:      mustJSON(request.Arguments),
		Summary:        request.Summary,
		Diff:           diff,
		TargetID:       request.TargetID,
		TargetRead:     mustJSON(targetRead{Operation: request.ReadOperation, Arguments: request.ReadArguments}),
		TargetVersion:  version,
		Destructive:    operation.Destructive || request.DestructiveHint || in.ForceDestructive,
		State:          store.StatePending,
	}
	if err := d.Store.InsertProposal(ctx, proposal); err != nil {
		return ProposalView{}, err
	}
	if err := d.Audit.Proposal(ctx, proposal, "proposed"); err != nil {
		return ProposalView{}, err
	}
	return ProposalView{ID: proposal.ID, Operation: proposal.Operation, Summary: proposal.Summary, TargetID: proposal.TargetID, Destructive: proposal.Destructive, State: store.StatePending, Diff: proposal.Diff}, nil
}

func (d *Deps) ExpireProposal(ctx context.Context, in ExpireInput) (ProposalView, error) {
	proposal, err := d.Store.Advance(ctx, in.ID, store.EventExpire, "", nil)
	if errors.Is(err, store.ErrInvalidTransition) {
		return ProposalView{ID: in.ID, State: proposal.State}, nil
	}
	if err != nil {
		return ProposalView{}, err
	}
	if err := d.Audit.Proposal(ctx, proposal, "expired"); err != nil {
		return ProposalView{}, err
	}
	return ProposalView{ID: in.ID, State: proposal.State}, nil
}

func (d *Deps) revalidate(ctx context.Context, person, athlete, operation string) error {
	identity, err := d.Access.Resolve(ctx, person, athlete)
	if err != nil {
		return err
	}
	if !identity.Has(tools.Permission(operation)) {
		return access.ErrDenied
	}
	return nil
}

func (d *Deps) Commit(ctx context.Context, in CommitInput) (CommitOutput, error) {
	proposal, err := d.Store.Proposal(ctx, in.ProposalID)
	if err != nil {
		return CommitOutput{}, err
	}
	if proposal.State == store.StateCommitted {
		return CommitOutput{Outcome: "committed", Text: string(proposal.CommitResult)}, nil
	}
	if proposal.State != store.StateApproved && proposal.State != store.StateCommitting {
		return CommitOutput{Outcome: string(proposal.State), Text: "proposal is not approved"}, nil
	}
	var read targetRead
	if err := json.Unmarshal(proposal.TargetRead, &read); err != nil {
		return CommitOutput{}, err
	}
	if proposal, err = d.Store.Advance(ctx, in.ProposalID, store.EventBeginCommit, "", nil); err != nil {
		return CommitOutput{}, err
	}
	finish := func(event store.Event, outcome, text string, jti string) (CommitOutput, error) {
		result := mustJSON(map[string]any{"outcome": outcome, "text": agent.Truncate(text, 4000)})
		advanced, err := d.Store.Advance(ctx, in.ProposalID, event, "", result)
		if err != nil {
			return CommitOutput{}, err
		}
		if err := d.Audit.Commit(ctx, advanced, jti, outcome, map[string]any{"approver": proposal.ApproverPK}); err != nil {
			return CommitOutput{}, err
		}
		return CommitOutput{Outcome: outcome, Text: text}, nil
	}
	for _, person := range []string{proposal.RequesterPK, proposal.ApproverPK} {
		if err := d.revalidate(ctx, person, proposal.AthletePK, proposal.Operation); err != nil {
			if errors.Is(err, access.ErrDenied) {
				return finish(store.EventFail, "denied", "access was revoked before the change was applied", "")
			}
			return CommitOutput{}, err
		}
	}
	subject := Subject{Person: proposal.RequesterPK, Athlete: proposal.AthletePK, ConversationID: proposal.ConversationID, WorkflowID: proposal.WorkflowID, Scope: []string{read.Operation, proposal.Operation}}
	current, err := d.ToolCall(ctx, ToolCallInput{Subject: subject, Name: read.Operation, Arguments: read.Arguments})
	if err != nil {
		return CommitOutput{}, err
	}
	if current.IsError {
		return finish(store.EventFail, "failed", "target could not be re-read: "+current.Text, current.JTI)
	}
	if tools.Version(current.Text) != proposal.TargetVersion {
		return finish(store.EventStale, "stale", "the target changed after the proposal was made", current.JTI)
	}
	var arguments map[string]any
	if err := json.Unmarshal(proposal.Arguments, &arguments); err != nil {
		return CommitOutput{}, err
	}
	applied, err := d.ToolCall(ctx, ToolCallInput{Subject: subject, Name: proposal.Operation, Arguments: arguments, AllowMutation: true})
	if err != nil {
		return CommitOutput{}, fmt.Errorf("commit %s: %w", proposal.ID, err)
	}
	if applied.IsError {
		return finish(store.EventFail, "failed", applied.Text, applied.JTI)
	}
	return finish(store.EventCommit, "committed", applied.Text, applied.JTI)
}
