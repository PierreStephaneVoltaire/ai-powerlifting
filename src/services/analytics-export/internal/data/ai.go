package data

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"time"

	"powerlifting/analytics-export/internal/auth"
)

const aiTimeout = 10 * time.Second

// AIClient fetches cached (never regenerated) AI analysis reports for a
// finished block, so the export can include whatever the athlete already
// generated on the Past Blocks page without triggering a new generation.
type AIClient struct {
	Client  *http.Client
	BaseURL string
}

func NewAIClient(baseURL string) *AIClient {
	return &AIClient{Client: &http.Client{Timeout: aiTimeout}, BaseURL: baseURL}
}

func (a *AIClient) fetch(ctx context.Context, operation string, blockKey string, caller auth.Caller) (map[string]any, error) {
	body, err := json.Marshal(map[string]any{"pk": caller.Athlete, "block_key": blockKey, "cache_only": true})
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, a.BaseURL+"/operations/"+operation, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Person-Pk", caller.Person)
	request.Header.Set("X-Athlete-Pk", caller.Athlete)
	response, err := a.Client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, nil
	}
	var result map[string]any
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}

// BlockEvaluation returns the cached retrospective program evaluation for a
// finished block, or nil if none has been generated yet.
func (a *AIClient) BlockEvaluation(ctx context.Context, blockKey string, caller auth.Caller) (map[string]any, error) {
	return a.fetch(ctx, "block_program_evaluation", blockKey, caller)
}

// BlockCorrelation returns the cached ROI correlation report for a finished
// block, or nil if none has been generated yet.
func (a *AIClient) BlockCorrelation(ctx context.Context, blockKey string, caller auth.Caller) (map[string]any, error) {
	return a.fetch(ctx, "block_correlation_analysis", blockKey, caller)
}
