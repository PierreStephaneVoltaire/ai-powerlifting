package cache

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"powerlifting/analytics-ai/internal/pyjson"
)

const requestTimeout = 20 * time.Second

type Prompts struct {
	KV   KV
	URL  string
	HTTP *http.Client
	Now  func() time.Time
}

type promptContext struct {
	Date            string `json:"date"`
	AnalysisVersion string `json:"analysis_version"`
}

type promptBody struct {
	Athlete   string          `json:"athlete"`
	Operation string          `json:"operation"`
	Request   json.RawMessage `json:"request"`
	Response  json.RawMessage `json:"response,omitempty"`
	Context   promptContext   `json:"context"`
}

type lookupResult struct {
	Hit      bool            `json:"hit"`
	Layer    string          `json:"layer"`
	Response json.RawMessage `json:"response"`
}

func (p Prompts) body(ctx context.Context, athlete, operation string, request Request, response map[string]any) (promptBody, bool) {
	encoded, err := pyjson.Encode(request.value())
	if err != nil {
		return promptBody{}, false
	}
	body := promptBody{Athlete: athlete, Operation: operation, Request: encoded}
	now := time.Now
	if p.Now != nil {
		now = p.Now
	}
	body.Context = promptContext{Date: now().Format("2006-01-02"), AnalysisVersion: AnalysisVersion(ctx, p.KV, athlete)}
	if response != nil {
		answer, err := pyjson.Encode(response)
		if err != nil {
			return promptBody{}, false
		}
		body.Response = answer
	}
	return body, true
}

func (p Prompts) post(ctx context.Context, path string, body promptBody) ([]byte, bool) {
	if p.URL == "" {
		return nil, false
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, false
	}
	ctx, cancel := context.WithTimeout(ctx, requestTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(p.URL, "/")+path, bytes.NewReader(payload))
	if err != nil {
		return nil, false
	}
	request.Header.Set("Content-Type", "application/json")
	client := p.HTTP
	if client == nil {
		client = http.DefaultClient
	}
	response, err := client.Do(request)
	if err != nil {
		slog.Warn("prompt cache request failed", "path", path, "error", err)
		return nil, false
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil || response.StatusCode != http.StatusOK {
		slog.Warn("prompt cache request failed", "path", path, "status", response.StatusCode, "error", err)
		return nil, false
	}
	return raw, true
}

func (p Prompts) Lookup(ctx context.Context, athlete, operation string, request Request) (map[string]any, string, bool) {
	body, ok := p.body(ctx, athlete, operation, request, nil)
	if !ok {
		return nil, "", false
	}
	raw, ok := p.post(ctx, "/lookup", body)
	if !ok {
		return nil, "", false
	}
	var result lookupResult
	if err := json.Unmarshal(raw, &result); err != nil || !result.Hit {
		return nil, "", false
	}
	value, err := pyjson.Decode(result.Response)
	if err != nil {
		return nil, "", false
	}
	response, ok := value.(map[string]any)
	return response, result.Layer, ok
}

func (p Prompts) Remember(ctx context.Context, athlete, operation string, request Request, response map[string]any) {
	body, ok := p.body(ctx, athlete, operation, request, response)
	if ok {
		p.post(ctx, "/store", body)
	}
}
