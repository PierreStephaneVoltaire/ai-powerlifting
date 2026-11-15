package httpapi

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/workflow"
)

const (
	maxMessages    = 40
	maxMessageSize = 8000
)

type TurnRequest struct {
	Messages []llm.Message           `json:"messages"`
	Athlete  string                  `json:"athlete"`
	Surface  string                  `json:"surface"`
	Context  workflow.RequestContext `json:"context"`
}

func newJobID() (string, error) {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	return hex.EncodeToString(raw), nil
}

func validateTurn(request TurnRequest) error {
	if len(request.Messages) == 0 || len(request.Messages) > maxMessages {
		return errors.New("messages must hold between 1 and 40 entries")
	}
	for _, message := range request.Messages {
		if message.Role != "user" && message.Role != "assistant" {
			return errors.New("message roles must be user or assistant")
		}
		if len(message.Content) > maxMessageSize {
			return errors.New("message content is too large")
		}
	}
	last := request.Messages[len(request.Messages)-1]
	if last.Role != "user" || strings.TrimSpace(last.Content) == "" {
		return errors.New("the last message must be a non-empty user message")
	}
	if request.Surface != "" {
		if _, ok := tools.LookupSurface(request.Surface); !ok {
			return errors.New("unknown surface")
		}
	}
	return nil
}

func (s *Server) createTurn(w http.ResponseWriter, r *http.Request) {
	caller, ok := s.authorize(w, r)
	if !ok {
		return
	}
	ref, err := store.ParseConversationID(r.PathValue("conversation_id"))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, err.Error())
		return
	}
	var request TurnRequest
	if err := decode(r, &request); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := validateTurn(request); err != nil {
		writeError(w, http.StatusUnprocessableEntity, err.Error())
		return
	}
	for _, claimed := range []string{request.Athlete, caller.Athlete} {
		if claimed != "" && claimed != ref.Athlete {
			writeError(w, http.StatusForbidden, "Athlete does not match the conversation")
			return
		}
	}
	if !ref.Shared && ref.Owner != caller.Person {
		writeError(w, http.StatusForbidden, "conversation belongs to another Person")
		return
	}
	if _, err := s.Access.Resolve(r.Context(), caller.Person, ref.Athlete); err != nil {
		writeError(w, accessStatus(err), "no active access to this Athlete")
		return
	}
	jobID, err := newJobID()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not allocate a job")
		return
	}
	if err := s.Store.EnsureConversation(r.Context(), ref, caller.Person); err != nil {
		s.Log.Error("ensure conversation", "error", err)
		writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
		return
	}
	raw, _ := json.Marshal(request)
	if err := s.Store.InsertTurn(r.Context(), store.Turn{ID: jobID, ConversationID: ref.ID, PersonPK: caller.Person, WorkflowID: jobID, Status: "queued", Request: raw}); err != nil {
		s.Log.Error("insert turn", "error", err)
		writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
		return
	}
	input := workflow.TurnInput{TurnID: jobID, ConversationID: ref.ID, Person: caller.Person, Athlete: ref.Athlete, Surface: request.Surface, Messages: request.Messages, Context: request.Context}
	if err := s.Engine.Schedule(r.Context(), jobID, input); err != nil {
		s.Log.Error("schedule workflow", "error", err)
		_ = s.Store.CompleteTurn(r.Context(), store.Completion{TurnID: jobID, Status: "failed", Error: "workflow engine unavailable"})
		writeError(w, http.StatusServiceUnavailable, "workflow engine unavailable")
		return
	}
	turn, err := s.Store.Turn(r.Context(), jobID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "turn not readable")
		return
	}
	writeJSON(w, http.StatusAccepted, s.view(r, turn))
}
