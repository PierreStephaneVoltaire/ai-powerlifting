package domainjobs

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"powerlifting/assistant/internal/store"
)

const Deadline = 15 * time.Minute

type state struct {
	Next string          `json:"next"`
	Data json.RawMessage `json:"data"`
}

type problem struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Status  int    `json:"status,omitempty"`
}

func (p problem) Error() string { return p.Message }

func (s *Service) Step(ctx context.Context, input StepInput) (StepOutput, error) {
	job, claimed, err := s.Store.ClaimDomainStep(ctx, input.ID, input.Sequence)
	if err != nil {
		return StepOutput{}, err
	}
	var previous state
	if err := json.Unmarshal(job.State, &previous); err != nil {
		return StepOutput{}, err
	}
	if Terminal(job.Status) || job.Step != input.Sequence || (!claimed && !job.InFlight) {
		return StepOutput{Status: job.Status, Next: previous.Next}, nil
	}

	status := "running"
	var next state
	var result, failure json.RawMessage
	var workErr error
	deadline := job.CreatedAt.Add(Deadline)
	switch {
	case !claimed && input.Kind != "answer":
		workErr = problem{Code: "uncertain", Message: "The previous domain request may have completed. Check its result before retrying."}
	case input.Kind == "expire" || time.Now().After(deadline):
		workErr = problem{Code: "uncertain", Message: "The domain job timed out. Check its result before retrying."}
	default:
		workCtx, cancel := context.WithDeadline(ctx, deadline)
		next, result, workErr = s.advance(workCtx, job, previous, input.Kind)
		cancel()
	}
	if workErr != nil {
		status = "failed"
		p := problem{Code: "execution_failed", Message: workErr.Error()}
		if errors.As(workErr, &p) && p.Code == "uncertain" {
			status = "uncertain"
		}
		failure = marshal(p)
	} else if next.Next == "" {
		status = "succeeded"
	}

	job, err = s.Store.FinishDomainStep(ctx, job.ID, input.Sequence, status, marshal(next), result, failure)
	if err != nil {
		return StepOutput{}, err
	}
	return StepOutput{Status: job.Status, Next: next.Next}, nil
}

func (s *Service) advance(ctx context.Context, job store.DomainJob, previous state, kind string) (state, json.RawMessage, error) {
	var payload Payload
	if err := json.Unmarshal(job.Payload, &payload); err != nil {
		return state{}, nil, err
	}
	if payload.Arguments == nil {
		payload.Arguments = map[string]any{}
	}
	operation, ok := s.Catalog[payload.Operation]
	if !ok {
		return state{}, nil, errors.New("unknown domain operation")
	}
	if kind == "answer" {
		var challenge continuation
		if err := json.Unmarshal(previous.Data, &challenge); err != nil {
			return state{}, nil, err
		}
		arguments := payload.AccessArguments()
		arguments["_required_access"] = payload.Access
		identity, err := s.Access.ResolveOperation(ctx, job.Person, job.Athlete, payload.Operation, arguments)
		if err != nil || !identity.Has("ai:use") {
			return state{}, nil, problem{Code: "access_denied", Message: "Access to the domain operation expired or could not be verified"}
		}
		var report string
		if operation.Name == "template_evaluate" && s.Lifetime != nil {
			report, _ = s.Lifetime(ctx, job.Athlete)
		}
		answer, err := s.infer(ctx, s.Models[operation.Name], job.ID, job.Person, challenge, report)
		if err != nil {
			return state{}, nil, problem{Code: "model_failed", Message: "LiteLLM did not return a valid answer to the domain challenge"}
		}
		return state{Next: "resume", Data: marshal(answered{ExecutionID: challenge.ExecutionID, ChallengeID: challenge.ChallengeID, Content: answer})}, nil, nil
	}

	path := "/operations/" + operation.Name
	body := marshal(payload.Arguments)
	if kind == "poll" || kind == "resume" {
		var answer answered
		if err := json.Unmarshal(previous.Data, &answer); err != nil {
			return state{}, nil, err
		}
		if answer.ExecutionID == "" || strings.ContainsAny(answer.ExecutionID, "/?#") {
			return state{}, nil, errors.New("invalid domain execution ID")
		}
		path = "/executions/" + answer.ExecutionID
		body = json.RawMessage("{}")
		if kind == "resume" {
			body = marshal(map[string]any{"challenge_id": answer.ChallengeID, "content": answer.Content})
		}
	}

	raw, err := s.post(ctx, job, operation, payload, path, body)
	if err != nil {
		return state{}, nil, err
	}
	if !operation.Inference() {
		return state{}, raw, nil
	}
	var response continuation
	if err := json.Unmarshal(raw, &response); err != nil {
		return state{}, raw, nil
	}
	switch response.Status {
	case "needs_inference":
		return state{Next: "answer", Data: raw}, nil, nil
	case "running":
		return state{Next: "poll", Data: raw}, nil, nil
	case "succeeded":
		if len(response.Result) != 0 {
			return state{}, response.Result, nil
		}
	}
	return state{}, raw, nil
}

func (s *Service) post(ctx context.Context, job store.DomainJob, operation Operation, payload Payload, path string, body json.RawMessage) (json.RawMessage, error) {
	base := strings.ReplaceAll(s.ServiceURL, "{domain}", operation.Domain)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(base, "/")+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", job.Person)
	request.Header.Set("X-Athlete-Pk", job.Athlete)
	if operation.Inference() {
		request.Header.Set("X-IF-Turn-Id", job.ID)
	}
	if operation.Inference() && strings.HasPrefix(path, "/operations/") && payload.GenerationID != "" {
		request.Header.Set("X-IF-Generation-Id", payload.GenerationID)
		request.Header.Set("X-IF-Generation-Attempt", strconv.Itoa(payload.GenerationAttempt))
	}

	response, err := s.HTTP.Do(request)
	uncertain := problem{Code: "uncertain", Message: "Could not verify the domain request outcome. Check its result before retrying."}
	if err != nil {
		return nil, uncertain
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil || !json.Valid(raw) {
		return nil, uncertain
	}
	if response.StatusCode >= 400 {
		var detail struct {
			Detail problem `json:"detail"`
		}
		_ = json.Unmarshal(raw, &detail)
		if detail.Detail.Code == "uncertain" || response.StatusCode >= 500 {
			return nil, uncertain
		}
		message := detail.Detail.Message
		if message == "" {
			message = http.StatusText(response.StatusCode)
		}
		return nil, problem{Code: "service_error", Message: message, Status: response.StatusCode}
	}
	return raw, nil
}
