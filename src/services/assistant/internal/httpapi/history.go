package httpapi

import (
	"encoding/json"
	"net/http"
	"slices"
	"strconv"
	"strings"
	"time"

	"powerlifting/assistant/internal/store"
)

type HistoryContent struct {
	Request   string         `json:"request"`
	Reply     string         `json:"reply"`
	Progress  *ProgressItem  `json:"progress,omitempty"`
	Proposals []ProposalItem `json:"proposals"`
}

type HistoryItem struct {
	ID        string          `json:"id"`
	PersonPK  string          `json:"person_pk"`
	Status    string          `json:"status"`
	CreatedAt time.Time       `json:"created_at"`
	Summary   string          `json:"summary"`
	Error     string          `json:"error,omitempty"`
	Content   *HistoryContent `json:"content,omitempty"`
}

func lastUserText(request json.RawMessage) string {
	var parsed struct {
		Messages []struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"messages"`
	}
	if json.Unmarshal(request, &parsed) != nil {
		return ""
	}
	for index := len(parsed.Messages) - 1; index >= 0; index-- {
		if parsed.Messages[index].Role == "user" {
			return parsed.Messages[index].Content
		}
	}
	return ""
}

func (s *Server) history(w http.ResponseWriter, r *http.Request) {
	caller, ok := s.authorize(w, r)
	if !ok {
		return
	}
	ref, err := store.ParseConversationID(r.PathValue("conversation_id"))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, err.Error())
		return
	}
	identity, err := s.Access.Resolve(r.Context(), caller.Person, ref.Athlete)
	if err != nil {
		writeError(w, accessStatus(err), "no active access to this Athlete")
		return
	}
	query := r.URL.Query()
	limit, _ := strconv.Atoi(query.Get("limit"))
	turns, err := s.Store.History(r.Context(), store.HistoryQuery{
		ConversationID: ref.ID, Athlete: ref.Athlete, Person: caller.Person, Permissions: identity.Permissions, Before: query.Get("before"), Limit: limit,
	})
	if err != nil {
		s.Log.Error("history", "error", err)
		writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
		return
	}
	expand := strings.Split(query.Get("expand"), ",")
	expandAll := slices.Contains(expand, "all")
	items := make([]HistoryItem, 0, len(turns))
	for _, turn := range turns {
		item := HistoryItem{ID: turn.ID, PersonPK: turn.PersonPK, Status: turn.Status, CreatedAt: turn.CreatedAt, Summary: turn.Summary, Error: turn.Error}
		if expandAll || slices.Contains(expand, turn.ID) {
			item.Content = &HistoryContent{Request: lastUserText(turn.Request), Reply: turn.Reply}
			item.Content.Progress = s.progress(r, turn.ID)
			item.Content.Proposals = s.proposals(r, turn.ID)
		}
		items = append(items, item)
	}
	response := map[string]any{"conversation_id": ref.ID, "turns": items}
	if len(items) > 0 {
		response["next_before"] = items[len(items)-1].ID
	}
	writeJSON(w, http.StatusOK, response)
}
