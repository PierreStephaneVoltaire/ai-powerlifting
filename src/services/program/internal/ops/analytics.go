package ops

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"powerlifting/program/internal/pyval"
)

type Weekly struct {
	Data      map[string]any
	LiftOrder []string
}

type HTTPAnalytics struct {
	Client  *http.Client
	BaseURL string
}

func NewHTTPAnalytics(baseURL string) *HTTPAnalytics {
	return &HTTPAnalytics{Client: &http.Client{Timeout: 60 * time.Second}, BaseURL: baseURL}
}

func (a *HTTPAnalytics) WeeklyAnalysis(ctx context.Context, caller Caller, arguments map[string]any) (*Weekly, error) {
	body := map[string]any{}
	for key, value := range arguments {
		if value != nil {
			body[key] = value
		}
	}
	encoded, err := json.Marshal(pyval.Coerce(body))
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, a.BaseURL+"/operations/weekly_analysis", bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	if caller.ActiveJob != "" {
		request.Header.Set("X-IF-Turn-Id", caller.ActiveJob)
		request.Header.Set("X-PL-Nested-Operation", "true")
	}
	response, err := a.Client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("analytics service unreachable: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest {
		return nil, fmt.Errorf("analytics service returned %d", response.StatusCode)
	}
	var buffer bytes.Buffer
	if _, err := buffer.ReadFrom(response.Body); err != nil {
		return nil, err
	}
	decoded, err := pyval.Decode(buffer.Bytes())
	if err != nil {
		return nil, err
	}
	result, _ := decoded.(map[string]any)
	return &Weekly{Data: result, LiftOrder: pyval.KeyOrder(buffer.Bytes(), "lifts")}, nil
}
