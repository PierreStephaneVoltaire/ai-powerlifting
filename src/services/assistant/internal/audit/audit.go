package audit

import (
	"context"
	"log/slog"

	"powerlifting/assistant/internal/store"
)

type Recorder struct {
	Store *store.Store
	Log   *slog.Logger
}

func (r *Recorder) Record(ctx context.Context, entry store.AuditEntry) error {
	r.Log.Info("audit", "kind", entry.Kind, "person_pk", entry.PersonPK, "conversation_id", entry.ConversationID, "jti", entry.JTI, "operation", entry.Operation, "decision", entry.Decision)
	return r.Store.Audit(ctx, entry)
}

func (r *Recorder) Access(ctx context.Context, person, athlete, conversationID, workflowID, decision, reason string) error {
	return r.Record(ctx, store.AuditEntry{Kind: "access", PersonPK: person, AthletePK: athlete, ConversationID: conversationID, WorkflowID: workflowID, Decision: decision, Detail: map[string]any{"reason": reason}})
}

func (r *Recorder) Tool(ctx context.Context, person, athlete, conversationID, workflowID, jti, operation, decision string, detail map[string]any) error {
	return r.Record(ctx, store.AuditEntry{Kind: "tool_call", PersonPK: person, AthletePK: athlete, ConversationID: conversationID, WorkflowID: workflowID, JTI: jti, Operation: operation, Decision: decision, Detail: detail})
}

func (r *Recorder) Proposal(ctx context.Context, proposal store.Proposal, decision string) error {
	return r.Record(ctx, store.AuditEntry{Kind: "proposal", PersonPK: proposal.RequesterPK, AthletePK: proposal.AthletePK, ConversationID: proposal.ConversationID, WorkflowID: proposal.WorkflowID, Operation: proposal.Operation, Decision: decision,
		Detail: map[string]any{"proposal_id": proposal.ID, "target_id": proposal.TargetID, "target_version": proposal.TargetVersion, "destructive": proposal.Destructive}})
}

func (r *Recorder) Approval(ctx context.Context, proposal store.Proposal, approver, decision string) error {
	return r.Record(ctx, store.AuditEntry{Kind: "approval", PersonPK: approver, AthletePK: proposal.AthletePK, ConversationID: proposal.ConversationID, WorkflowID: proposal.WorkflowID, Operation: proposal.Operation, Decision: decision,
		Detail: map[string]any{"proposal_id": proposal.ID, "target_id": proposal.TargetID, "requester": proposal.RequesterPK}})
}

func (r *Recorder) Commit(ctx context.Context, proposal store.Proposal, jti, decision string, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	detail["proposal_id"] = proposal.ID
	detail["target_id"] = proposal.TargetID
	return r.Record(ctx, store.AuditEntry{Kind: "commit", PersonPK: proposal.RequesterPK, AthletePK: proposal.AthletePK, ConversationID: proposal.ConversationID, WorkflowID: proposal.WorkflowID, JTI: jti, Operation: proposal.Operation, Decision: decision, Detail: detail})
}
