package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"

	"powerlifting/assistant/internal/store"
)

type ProposalItem struct {
	ID          string          `json:"id"`
	Operation   string          `json:"operation"`
	Summary     string          `json:"summary"`
	TargetID    string          `json:"target_id"`
	Destructive bool            `json:"destructive"`
	State       store.State     `json:"state"`
	Diff        json.RawMessage `json:"diff"`
	CommitError string          `json:"commit_error,omitempty"`
}

func proposalItem(proposal store.Proposal) ProposalItem {
	item := ProposalItem{
		ID: proposal.ID, Operation: proposal.Operation, Summary: proposal.Summary, TargetID: proposal.TargetID,
		Destructive: proposal.Destructive, State: proposal.State, Diff: proposal.Diff,
	}
	if proposal.State == store.StateFailed || proposal.State == store.StateStale {
		item.CommitError = commitErrorText(proposal.CommitResult)
	}
	return item
}

func commitErrorText(result json.RawMessage) string {
	var parsed struct {
		Text string `json:"text"`
	}
	if json.Unmarshal(result, &parsed) == nil && parsed.Text != "" {
		return parsed.Text
	}
	return string(result)
}

type JobView struct {
	ID             string         `json:"id"`
	JobID          string         `json:"job_id"`
	Status         string         `json:"status"`
	Kind           string         `json:"kind"`
	ConversationID string         `json:"conversation_id"`
	CreatedAt      string         `json:"created_at"`
	UpdatedAt      string         `json:"updated_at"`
	Error          string         `json:"error"`
	Artifacts      []string       `json:"artifacts"`
	Result         *JobResult     `json:"result"`
	Proposals      []ProposalItem `json:"proposals"`
	Activity       []ActivityItem `json:"activity"`
	Progress       *ProgressItem  `json:"progress"`
}

type ProgressItem struct {
	Stage     string `json:"stage"`
	Text      string `json:"text"`
	UpdatedAt string `json:"updated_at"`
}

type ActivityItem struct {
	At      string `json:"at"`
	Kind    string `json:"kind"`
	Model   string `json:"model"`
	Outcome string `json:"outcome"`
	Label   string `json:"label"`
}

const activityLimit = 8

func activityLabel(event store.ActivityEvent) string {
	switch event.Kind {
	case "orchestrate":
		return "planning"
	case "delegate":
		if event.Web {
			return "searching the web"
		}
		return "working on a subtask"
	case "escalate":
		return "retrying on a stronger model"
	case "review":
		return "checking results"
	case "security":
		return "security check"
	}
	return event.Kind
}

type JobResult struct {
	Content string `json:"content"`
}

func terminal(status string) bool {
	switch status {
	case "succeeded", "failed", "cancelled":
		return true
	}
	return false
}

func (s *Server) progress(r *http.Request, turnID string) *ProgressItem {
	progress, err := s.Store.Progress(r.Context(), turnID)
	if err != nil || progress == nil {
		return nil
	}
	return &ProgressItem{Stage: progress.Stage, Text: progress.Text, UpdatedAt: progress.UpdatedAt.UTC().Format("2006-01-02T15:04:05Z")}
}

func (s *Server) proposals(r *http.Request, turnID string) []ProposalItem {
	items := []ProposalItem{}
	if proposals, err := s.Store.ProposalsForTurn(r.Context(), turnID); err == nil {
		for _, proposal := range proposals {
			items = append(items, proposalItem(proposal))
		}
	}
	return items
}

func (s *Server) view(r *http.Request, turn store.Turn) JobView {
	view := JobView{
		ID: turn.ID, JobID: turn.ID, Status: turn.Status, Kind: "conversation", ConversationID: turn.ConversationID,
		CreatedAt: turn.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"), UpdatedAt: turn.UpdatedAt.UTC().Format("2006-01-02T15:04:05Z"),
		Error: turn.Error, Artifacts: []string{}, Proposals: []ProposalItem{}, Activity: []ActivityItem{},
	}
	if !terminal(turn.Status) {
		if engine, err := s.Engine.Status(r.Context(), turn.WorkflowID); err == nil {
			switch engine.Status {
			case "failed", "cancelled":
				_ = s.Store.CompleteTurn(r.Context(), store.Completion{TurnID: turn.ID, Status: engine.Status, Error: engine.Error})
				view.Status, view.Error = engine.Status, engine.Error
			case "uncertain":
				view.Status, view.Error = "uncertain", engine.Error
			case "succeeded":
				if fresh, err := s.Store.Turn(r.Context(), turn.ID); err == nil {
					turn = fresh
					view.Status, view.Error = turn.Status, turn.Error
				}
			}
		}
	}
	if !terminal(view.Status) {
		if events, err := s.Store.RecentActivity(r.Context(), turn.PersonPK, turn.WorkflowID, activityLimit); err == nil {
			for _, event := range events {
				view.Activity = append(view.Activity, ActivityItem{At: event.At.UTC().Format("2006-01-02T15:04:05Z"), Kind: event.Kind, Model: event.Model, Outcome: event.Outcome, Label: activityLabel(event)})
			}
		}
	}
	view.Progress = s.progress(r, turn.ID)
	if turn.Status == "succeeded" || (turn.Status == "failed" && turn.Reply != "") {
		view.Result = &JobResult{Content: turn.Reply}
	}
	view.Proposals = s.proposals(r, turn.ID)
	return view
}

func (s *Server) ownTurn(w http.ResponseWriter, r *http.Request) (store.Turn, bool) {
	caller, ok := s.authorize(w, r)
	if !ok {
		return store.Turn{}, false
	}
	turn, err := s.Store.Turn(r.Context(), r.PathValue("id"))
	if errors.Is(err, store.ErrNotFound) || (err == nil && turn.PersonPK != caller.Person) {
		writeError(w, http.StatusNotFound, "job not found")
		return store.Turn{}, false
	}
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
		return store.Turn{}, false
	}
	return turn, true
}

func (s *Server) job(result bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if s.domainJob(w, r, result, false) {
			return
		}
		turn, ok := s.ownTurn(w, r)
		if !ok {
			return
		}
		view := s.view(r, turn)
		status := http.StatusOK
		if result && !terminal(view.Status) {
			status = http.StatusAccepted
		}
		writeJSON(w, status, view)
	}
}

func (s *Server) cancel(w http.ResponseWriter, r *http.Request) {
	if s.domainJob(w, r, false, true) {
		return
	}
	turn, ok := s.ownTurn(w, r)
	if !ok {
		return
	}
	if !terminal(turn.Status) {
		if err := s.Engine.Terminate(r.Context(), turn.WorkflowID); err != nil {
			s.Log.Warn("terminate workflow", "job", turn.ID, "error", err)
		}
		if err := s.Store.CancelTurn(r.Context(), turn.ID); err != nil {
			writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
			return
		}
		if proposals, err := s.Store.ProposalsForTurn(r.Context(), turn.ID); err == nil {
			for _, proposal := range proposals {
				if proposal.State == store.StatePending || proposal.State == store.StateApproved {
					_, _ = s.Store.Advance(r.Context(), proposal.ID, store.EventCancel, "", nil)
				}
			}
		}
		turn, _ = s.Store.Turn(r.Context(), turn.ID)
	}
	writeJSON(w, http.StatusOK, s.view(r, turn))
}
