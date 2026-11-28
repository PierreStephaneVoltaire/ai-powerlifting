package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"slices"
	"strings"
	"time"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/audit"
	"powerlifting/assistant/internal/domainjobs"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/workflow"
)

const (
	maxBodyBytes   = 256 * 1024
	requestTimeout = 30 * time.Second
)

type Engine interface {
	Schedule(ctx context.Context, id string, input workflow.TurnInput) error
	ScheduleDomain(ctx context.Context, id string) error
	Status(ctx context.Context, id string) (workflow.EngineStatus, error)
	Terminate(ctx context.Context, id string) error
	RaiseApproval(ctx context.Context, workflowID, proposalID string, event activities.ApprovalEvent) error
}

type Server struct {
	Store          *store.Store
	Access         *access.Client
	Audit          *audit.Recorder
	Engine         Engine
	DomainJobs     *domainjobs.Service
	Log            *slog.Logger
	AllowedCallers []string
	Now            func() time.Time
}

type Caller struct {
	Person  string
	Athlete string
	Source  string
}

func callerOf(r *http.Request) Caller {
	return Caller{
		Person:  r.Header.Get("X-Person-Pk"),
		Athlete: r.Header.Get("X-Athlete-Pk"),
		Source:  r.Header.Get("X-PL-Source-Principal"),
	}
}

func serviceAccount(source string) string {
	index := strings.LastIndex(source, "/sa/")
	if index < 0 {
		return ""
	}
	return source[index+len("/sa/"):]
}

func (s *Server) authorize(w http.ResponseWriter, r *http.Request) (Caller, bool) {
	caller := callerOf(r)
	if !slices.Contains(s.AllowedCallers, serviceAccount(caller.Source)) {
		writeError(w, http.StatusForbidden, "caller is not allowed")
		return caller, false
	}
	if caller.Person == "" {
		writeError(w, http.StatusForbidden, "authenticated Person scope required")
		return caller, false
	}
	return caller, true
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message, "detail": message})
}

func decode(r *http.Request, into any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, maxBodyBytes+1))
	if err != nil {
		return err
	}
	if len(body) > maxBodyBytes {
		return errors.New("request body too large")
	}
	if len(body) == 0 {
		return nil
	}
	return json.Unmarshal(body, into)
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /v1/conversations", s.listConversations)
	mux.HandleFunc("POST /v1/conversations/{conversation_id}/turns", s.createTurn)
	mux.HandleFunc("GET /v1/conversations/{conversation_id}/history", s.history)
	mux.HandleFunc("GET /v1/jobs/{id}", s.job(false))
	mux.HandleFunc("POST /v1/jobs", s.submitDomain)
	mux.HandleFunc("GET /v1/jobs/{id}/result", s.job(true))
	mux.HandleFunc("POST /v1/jobs/{id}/cancel", s.cancel)
	mux.HandleFunc("POST /v1/proposals/{id}/approve", s.decide(true))
	mux.HandleFunc("POST /v1/proposals/{id}/reject", s.decide(false))
	return http.TimeoutHandler(mux, requestTimeout, `{"error":"request timed out"}`)
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	if err := s.Store.Ping(r.Context()); err != nil {
		writeError(w, http.StatusServiceUnavailable, "database unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func accessStatus(err error) int {
	if errors.Is(err, access.ErrDenied) {
		return http.StatusForbidden
	}
	return http.StatusServiceUnavailable
}
