package coach

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/pyjson"
)

const (
	submitTimeout = 40 * time.Second
	statusTimeout = 15 * time.Second
)

type Job struct {
	ID     string `json:"job_id"`
	Status string `json:"status"`
	Error  any    `json:"error"`
}

type Submission struct {
	Domain            string
	Operation         string
	Arguments         map[string]any
	Athlete           string
	Person            string
	Key               string
	GenerationID      string
	GenerationAttempt int
}

type Client interface {
	Submit(ctx context.Context, submission Submission) (Job, error)
	Status(ctx context.Context, person, athlete, jobID string) (Job, error)
}

type HTTP struct {
	URL    string
	Client *http.Client
}

func (h HTTP) Submit(ctx context.Context, submission Submission) (Job, error) {
	payload := map[string]any{"domain": submission.Domain, "operation": submission.Operation, "arguments": submission.Arguments, "athlete": submission.Athlete}
	if submission.GenerationID != "" {
		payload["generation_id"] = submission.GenerationID
		payload["generation_attempt"] = submission.GenerationAttempt
	}
	body, err := pyjson.Encode(map[string]any{
		"conversation_id": "powerlifting:" + submission.Athlete + ":" + submission.Key,
		"kind":            "domain",
		"payload":         payload,
	})
	if err != nil {
		return Job{}, err
	}
	ctx, cancel := context.WithTimeout(ctx, submitTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(h.URL, "/")+"/v1/jobs", bytes.NewReader(body))
	if err != nil {
		return Job{}, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", submission.Person)
	request.Header.Set("X-Athlete-Pk", submission.Athlete)
	return h.do(request)
}

func (h HTTP) Status(ctx context.Context, person, athlete, jobID string) (Job, error) {
	ctx, cancel := context.WithTimeout(ctx, statusTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(h.URL, "/")+"/v1/jobs/"+jobID, nil)
	if err != nil {
		return Job{}, err
	}
	request.Header.Set("X-Person-Pk", person)
	request.Header.Set("X-Athlete-Pk", athlete)
	return h.do(request)
}

func (h HTTP) do(request *http.Request) (Job, error) {
	response, err := h.Client.Do(request)
	if err != nil {
		return Job{}, err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil {
		return Job{}, err
	}
	if response.StatusCode >= http.StatusBadRequest {
		if response.StatusCode == http.StatusTooManyRequests {
			return Job{}, apperr.Busy(string(raw))
		}
		return Job{}, apperr.ExecutionFailed(response.StatusCode, string(raw))
	}
	var job Job
	if err := json.Unmarshal(raw, &job); err != nil {
		return Job{}, fmt.Errorf("coach response: %w", err)
	}
	return job, nil
}
