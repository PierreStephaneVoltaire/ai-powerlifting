package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"slices"
	"strings"

	"powerlifting/assistant/internal/domainjobs"
	"powerlifting/assistant/internal/store"
)

const maxDomainJobBytes = 33 << 20

var domainJobCallers = []string{
	"powerlifting-app-backend", "pl-analytics", "pl-analytics-ai", "pl-glossary", "pl-imports", "pl-lift-profiles", "pl-templates",
}

func domainCaller(caller Caller) bool {
	return slices.Contains(domainJobCallers, serviceAccount(caller.Source))
}

type domainJobView struct {
	ID             string          `json:"job_id"`
	Kind           string          `json:"kind"`
	ConversationID string          `json:"conversation_id"`
	Status         string          `json:"status"`
	Result         *JobResult      `json:"result"`
	Error          json.RawMessage `json:"error"`
	Artifacts      []any           `json:"artifacts"`
	CreatedAt      int64           `json:"created_at"`
	UpdatedAt      int64           `json:"updated_at"`
}

func viewDomain(job store.DomainJob) domainJobView {
	view := domainJobView{
		ID: job.ID, Kind: "domain", ConversationID: job.ConversationID,
		Status: job.Status, Error: job.Error, Artifacts: []any{}, CreatedAt: job.CreatedAt.Unix(), UpdatedAt: job.UpdatedAt.Unix(),
	}
	if len(job.Result) > 0 && string(job.Result) != "null" {
		content := string(job.Result)
		_ = json.Unmarshal(job.Result, &content)
		view.Result = &JobResult{Content: content}
	}
	return view
}

func (s *Server) submitDomain(w http.ResponseWriter, r *http.Request) {
	if s.DomainJobs == nil {
		writeError(w, http.StatusNotFound, "domain jobs are unavailable")
		return
	}
	caller := callerOf(r)
	if !domainCaller(caller) || caller.Person == "" {
		writeError(w, http.StatusForbidden, "authenticated domain job caller required")
		return
	}
	var request struct {
		Kind    string             `json:"kind"`
		Payload domainjobs.Payload `json:"payload"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxDomainJobBytes))
	decoder.UseNumber()
	if err := decoder.Decode(&request); err != nil || request.Kind != "domain" {
		writeError(w, http.StatusUnprocessableEntity, "a valid domain job is required")
		return
	}
	payload := request.Payload
	operation, ok := s.DomainJobs.Catalog[payload.Operation]
	if !ok {
		writeError(w, http.StatusUnprocessableEntity, "unknown domain operation")
		return
	}
	if payload.Arguments == nil {
		payload.Arguments = map[string]any{}
	}
	if err := operation.Validate(payload.Arguments); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "invalid domain operation arguments")
		return
	}
	if payload.Athlete == "" || payload.Athlete != caller.Athlete || domainjobs.ScopeConflict(payload.Arguments, payload.Athlete) ||
		!domainjobs.TrustedArguments(payload.Arguments, serviceAccount(caller.Source), operation.Domain) {
		writeError(w, http.StatusForbidden, "job payload conflicts with the authorized operation or Athlete")
		return
	}
	identity, err := s.Access.ResolveOperation(r.Context(), caller.Person, payload.Athlete, operation.Name, payload.AccessArguments())
	if err != nil {
		writeError(w, accessStatus(err), "domain operation access denied")
		return
	}
	if operation.Inference() && !identity.Has("ai:use") {
		writeError(w, http.StatusForbidden, "AI access requires the pro group")
		return
	}

	required := []string{}
	for _, permission := range identity.Permissions {
		if strings.HasSuffix(permission, ":read") && !slices.Contains([]string{"settings:read", "grants:read", "operator:read"}, permission) {
			required = append(required, permission)
		}
	}
	slices.Sort(required)
	payload.Access, _ = json.Marshal(map[string][]string{
		"permissions": required, "competition_ids": identity.CompetitionRead,
	})
	payload.Domain = operation.Domain
	raw, err := json.Marshal(payload)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "invalid domain job payload")
		return
	}
	id, err := newJobID()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not allocate a job")
		return
	}
	job := store.DomainJob{
		ID: id, Person: caller.Person, Athlete: payload.Athlete, Status: "queued",
		ConversationID: "powerlifting:" + payload.Athlete + ":" + id, Payload: raw,
	}
	if err := s.Store.CreateDomainJob(r.Context(), job); err != nil {
		writeError(w, http.StatusServiceUnavailable, "domain job store unavailable")
		return
	}
	if err := s.Engine.ScheduleDomain(r.Context(), id); err != nil {
		s.Log.Warn("schedule domain job", "job_id", id, "error", err)
		writeError(w, http.StatusServiceUnavailable, "workflow scheduling could not be confirmed")
		return
	}
	job, err = s.Store.DomainJob(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "domain job store unavailable")
		return
	}
	writeJSON(w, http.StatusAccepted, viewDomain(job))
}

func (s *Server) domainJob(w http.ResponseWriter, r *http.Request, result, cancel bool) bool {
	caller := callerOf(r)
	if s.DomainJobs == nil || !domainCaller(caller) || caller.Person == "" {
		return false
	}
	job, err := s.Store.DomainJob(r.Context(), r.PathValue("id"))
	if errors.Is(err, store.ErrNotFound) {
		return false
	}
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "domain job store unavailable")
		return true
	}
	if cancel && job.Person != caller.Person {
		writeError(w, http.StatusForbidden, "only the submitting Person may cancel this job")
		return true
	}
	var payload domainjobs.Payload
	if err := json.Unmarshal(job.Payload, &payload); err != nil {
		writeError(w, http.StatusServiceUnavailable, "domain job data unavailable")
		return true
	}
	arguments := payload.AccessArguments()
	arguments["cache_only"] = true
	arguments["refresh"] = false
	arguments["_required_access"] = payload.Access
	if _, err := s.Access.ResolveOperation(r.Context(), caller.Person, job.Athlete, payload.Operation, arguments); err != nil {
		writeError(w, accessStatus(err), "domain job access denied")
		return true
	}
	if cancel && !domainjobs.Terminal(job.Status) {
		job, err = s.Store.CancelDomainJob(r.Context(), job.ID)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "could not cancel domain job")
			return true
		}
		if err := s.Engine.Terminate(r.Context(), job.ID); err != nil {
			s.Log.Warn("terminate domain workflow", "job_id", job.ID, "error", err)
		}
	}
	view := viewDomain(job)
	if !domainjobs.Terminal(job.Status) {
		engine, err := s.Engine.Status(r.Context(), job.ID)
		if err == nil && (engine.Status == "failed" || engine.Status == "uncertain") {
			view.Status = "uncertain"
			view.Error = json.RawMessage(`{"code":"uncertain","message":"Workflow did not confirm the job outcome. Check its result before retrying."}`)
		}
	}
	status := http.StatusOK
	if result && !domainjobs.Terminal(view.Status) {
		status = http.StatusAccepted
	}
	writeJSON(w, status, view)
	return true
}
