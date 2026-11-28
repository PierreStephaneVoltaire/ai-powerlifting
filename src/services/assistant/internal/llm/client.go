package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const (
	chatTimeout  = 180 * time.Second
	maxBodyBytes = 8 << 20
)

type FunctionCall struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

type ToolCall struct {
	ID       string       `json:"id"`
	Type     string       `json:"type"`
	Function FunctionCall `json:"function"`
}

type Message struct {
	Role             string          `json:"role"`
	Content          string          `json:"content"`
	ToolCalls        []ToolCall      `json:"tool_calls,omitempty"`
	ToolCallID       string          `json:"tool_call_id,omitempty"`
	ReasoningDetails json.RawMessage `json:"reasoning_details,omitempty"`
}

type FunctionDef struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	Parameters  json.RawMessage `json:"parameters"`
}

type ToolDef struct {
	Type     string      `json:"type"`
	Function FunctionDef `json:"function"`
}

type Metadata struct {
	UserID         string
	ConversationID string
	WorkflowID     string
	TurnID         string
	Role           string
}

func (m Metadata) Empty() bool {
	return m == Metadata{}
}

func (m Metadata) Body() map[string]any {
	tags := []string{"assistant"}
	if m.Role != "" {
		tags = append(tags, "role:"+m.Role)
	}
	return map[string]any{
		"tags":       tags,
		"trace_id":   m.WorkflowID,
		"session_id": m.ConversationID,
		"spend_logs_metadata": map[string]any{
			"user_id": m.UserID, "conversation_id": m.ConversationID, "workflow_id": m.WorkflowID, "turn_id": m.TurnID, "role": m.Role,
		},
	}
}

func (m Metadata) Headers() map[string]string {
	headers := map[string]string{}
	if m.UserID != "" {
		headers["x-litellm-customer-id"] = m.UserID
	}
	if m.WorkflowID != "" {
		headers["x-litellm-trace-id"] = m.WorkflowID
	}
	if m.ConversationID != "" {
		headers["x-litellm-session-id"] = m.ConversationID
	}
	if m.Role != "" {
		headers["x-litellm-tags"] = "assistant,role:" + m.Role
	}
	return headers
}

type ChatRequest struct {
	Meta            Metadata        `json:"-"`
	Private         bool            `json:"-"`
	Cache           map[string]bool `json:"cache,omitempty"`
	NoLog           bool            `json:"no-log,omitempty"`
	Store           *bool           `json:"store,omitempty"`
	Model           string          `json:"model"`
	Messages        []Message       `json:"messages"`
	Tools           []ToolDef       `json:"tools,omitempty"`
	ResponseFormat  any             `json:"response_format,omitempty"`
	ReasoningEffort string          `json:"reasoning_effort,omitempty"`
	MaxTokens       int             `json:"max_tokens,omitempty"`
	User            string          `json:"user,omitempty"`
	Metadata        any             `json:"metadata,omitempty"`
}

type ChatResponse struct {
	Content          string          `json:"content"`
	ToolCalls        []ToolCall      `json:"tool_calls"`
	FinishReason     string          `json:"finish_reason"`
	PromptTokens     int             `json:"prompt_tokens"`
	CompletionTokens int             `json:"completion_tokens"`
	ReasoningDetails json.RawMessage `json:"-"`
}

type Client struct {
	BaseURL string
	APIKey  string
	HTTP    *http.Client
}

func New(baseURL, apiKey string) *Client {
	return &Client{BaseURL: baseURL, APIKey: apiKey, HTTP: &http.Client{Timeout: chatTimeout}}
}

func (c *Client) post(ctx context.Context, path string, payload any, meta Metadata, private bool, out any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+c.APIKey)
	if private {
		request.Header.Set("Cache-Control", "no-store")
	}
	for name, value := range meta.Headers() {
		request.Header.Set(name, value)
	}
	response, err := c.HTTP.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxBodyBytes+1))
	if err != nil {
		return err
	}
	if len(raw) > maxBodyBytes {
		return fmt.Errorf("litellm %s response exceeds %d bytes; response was not processed", path, maxBodyBytes)
	}
	if response.StatusCode != http.StatusOK {
		if private {
			return fmt.Errorf("private litellm %s request failed with status %d", path, response.StatusCode)
		}
		return responseError(response.StatusCode, raw)
	}
	return json.Unmarshal(raw, out)
}

func (c *Client) Chat(ctx context.Context, request ChatRequest) (ChatResponse, error) {
	var payload struct {
		Choices []struct {
			Message      Message `json:"message"`
			FinishReason string  `json:"finish_reason"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
		} `json:"usage"`
	}
	if !request.Meta.Empty() {
		request.User = request.Meta.UserID
		request.Metadata = request.Meta.Body()
	}
	if request.Private {
		store := false
		request.Cache = map[string]bool{"no-store": true, "no-cache": true}
		request.NoLog = true
		request.Store = &store
	}
	if err := c.post(ctx, "/v1/chat/completions", request, request.Meta, request.Private, &payload); err != nil {
		return ChatResponse{}, err
	}
	if len(payload.Choices) == 0 {
		return ChatResponse{}, fmt.Errorf("model %s returned no choices", request.Model)
	}
	choice := payload.Choices[0]
	return ChatResponse{
		Content:          choice.Message.Content,
		ToolCalls:        choice.Message.ToolCalls,
		FinishReason:     choice.FinishReason,
		PromptTokens:     payload.Usage.PromptTokens,
		CompletionTokens: payload.Usage.CompletionTokens,
		ReasoningDetails: choice.Message.ReasoningDetails,
	}, nil
}

func (c *Client) Embed(ctx context.Context, model string, input string, meta Metadata) ([]float32, error) {
	return c.embed(ctx, model, input, meta, false)
}

func (c *Client) EmbedPrivate(ctx context.Context, model, input string) ([]float32, error) {
	return c.embed(ctx, model, input, Metadata{}, true)
}

func (c *Client) embed(ctx context.Context, model, input string, meta Metadata, private bool) ([]float32, error) {
	var payload struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	body := map[string]any{"model": model, "input": input}
	if !meta.Empty() {
		body["user"] = meta.UserID
		body["metadata"] = meta.Body()
	}
	if private {
		body["cache"] = map[string]bool{"no-store": true, "no-cache": true}
		body["no-log"] = true
	}
	if err := c.post(ctx, "/v1/embeddings", body, meta, private, &payload); err != nil {
		if private {
			return nil, fmt.Errorf("private embedding request failed")
		}
		return nil, err
	}
	if len(payload.Data) == 0 || len(payload.Data[0].Embedding) == 0 {
		if private {
			return nil, fmt.Errorf("private embedding returned no vector")
		}
		return nil, fmt.Errorf("model %s returned no embedding", model)
	}
	return payload.Data[0].Embedding, nil
}
