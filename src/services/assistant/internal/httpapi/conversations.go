package httpapi

import (
	"net/http"
)

func (s *Server) listConversations(w http.ResponseWriter, r *http.Request) {
	caller, ok := s.authorize(w, r)
	if !ok {
		return
	}
	if caller.Athlete == "" {
		writeError(w, http.StatusUnprocessableEntity, "athlete scope required")
		return
	}
	identity, err := s.Access.Resolve(r.Context(), caller.Person, caller.Athlete)
	if err != nil {
		writeError(w, accessStatus(err), "no active access to this Athlete")
		return
	}
	items, err := s.Store.ListGeneralConversations(r.Context(), caller.Athlete, caller.Person, identity.Permissions)
	if err != nil {
		s.Log.Error("list conversations", "error", err)
		writeError(w, http.StatusServiceUnavailable, "conversation store unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"conversations": items})
}
