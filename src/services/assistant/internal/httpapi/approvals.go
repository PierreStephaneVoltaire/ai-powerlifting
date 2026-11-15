package httpapi

import (
	"errors"
	"net/http"

	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

type DecisionRequest struct {
	Target string `json:"target"`
}

func approverAllowed(ref store.ConversationRef, person string, participant bool) bool {
	if ref.Shared {
		return participant
	}
	return ref.Owner == person
}

func (s *Server) decide(approve bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		caller, ok := s.authorize(w, r)
		if !ok {
			return
		}
		var body DecisionRequest
		if err := decode(r, &body); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		proposal, err := s.Store.Proposal(r.Context(), r.PathValue("id"))
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, http.StatusNotFound, "proposal not found")
			return
		}
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
			return
		}
		ref, err := store.ParseConversationID(proposal.ConversationID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "proposal conversation is malformed")
			return
		}
		participant, err := s.Store.IsParticipant(r.Context(), proposal.ConversationID, caller.Person)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
			return
		}
		if !approverAllowed(ref, caller.Person, participant) {
			writeError(w, http.StatusNotFound, "proposal not found")
			return
		}
		identity, err := s.Access.Resolve(r.Context(), caller.Person, proposal.AthletePK)
		if err != nil {
			writeError(w, accessStatus(err), "no active access to this Athlete")
			return
		}
		if !identity.Has(tools.Permission(proposal.Operation)) {
			s.record(r, proposal, caller.Person, "deny_permission")
			writeError(w, http.StatusForbidden, "approver lacks permission for this change")
			return
		}
		if approve && proposal.Destructive && body.Target != proposal.TargetID {
			s.record(r, proposal, caller.Person, "deny_target_mismatch")
			writeError(w, http.StatusUnprocessableEntity, "destructive changes require the exact target id")
			return
		}
		event, name := store.EventReject, "rejected"
		if approve {
			event, name = store.EventApprove, "approved"
		}
		advanced, err := s.Store.Advance(r.Context(), proposal.ID, event, caller.Person, nil)
		switch {
		case errors.Is(err, store.ErrInvalidTransition):
			repeat := (approve && advanced.State == store.StateApproved || !approve && advanced.State == store.StateRejected) && advanced.ApproverPK == caller.Person
			if !repeat {
				writeError(w, http.StatusConflict, "proposal is "+string(advanced.State))
				return
			}
		case err != nil:
			writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
			return
		default:
			s.record(r, advanced, caller.Person, name)
		}
		if err := s.Engine.RaiseApproval(r.Context(), proposal.WorkflowID, proposal.ID, activities.ApprovalEvent{Approve: approve, Approver: caller.Person}); err != nil {
			s.Log.Error("raise approval", "proposal", proposal.ID, "error", err)
			writeError(w, http.StatusBadGateway, "decision recorded but the workflow could not be notified; repeat the request")
			return
		}
		fresh, _ := s.Store.Proposal(r.Context(), proposal.ID)
		writeJSON(w, http.StatusOK, ProposalItem{
			ID: fresh.ID, Operation: fresh.Operation, Summary: fresh.Summary, TargetID: fresh.TargetID, Destructive: fresh.Destructive, State: fresh.State, Diff: fresh.Diff,
		})
	}
}

func (s *Server) record(r *http.Request, proposal store.Proposal, approver, decision string) {
	if err := s.Audit.Approval(r.Context(), proposal, approver, decision); err != nil {
		s.Log.Error("audit approval", "error", err)
	}
}
