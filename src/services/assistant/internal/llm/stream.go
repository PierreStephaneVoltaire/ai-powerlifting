package llm

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const maxStreamLine = 1 << 20

type streamToolCall struct {
	Index    int    `json:"index"`
	ID       string `json:"id"`
	Type     string `json:"type"`
	Function struct {
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	} `json:"function"`
}

type streamChunk struct {
	Choices []struct {
		Delta struct {
			Content          string           `json:"content"`
			ReasoningContent string           `json:"reasoning_content"`
			ToolCalls        []streamToolCall `json:"tool_calls"`
		} `json:"delta"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
}

func (c *Client) ChatStream(ctx context.Context, request ChatRequest, onDelta func(text string)) (ChatResponse, error) {
	if !request.Meta.Empty() {
		request.User = request.Meta.UserID
		request.Metadata = request.Meta.Body()
	}
	payload := struct {
		ChatRequest
		Stream        bool           `json:"stream"`
		StreamOptions map[string]any `json:"stream_options"`
	}{request, true, map[string]any{"include_usage": true}}
	body, err := json.Marshal(payload)
	if err != nil {
		return ChatResponse{}, err
	}
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return ChatResponse{}, err
	}
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Accept", "text/event-stream")
	httpRequest.Header.Set("Authorization", "Bearer "+c.APIKey)
	for name, value := range request.Meta.Headers() {
		httpRequest.Header.Set(name, value)
	}
	response, err := c.HTTP.Do(httpRequest)
	if err != nil {
		return ChatResponse{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 2048))
		return ChatResponse{}, responseError(response.StatusCode, raw)
	}
	var result ChatResponse
	var content strings.Builder
	calls := map[int]*ToolCall{}
	scanner := bufio.NewScanner(response.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), maxStreamLine)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		data, ok := strings.CutPrefix(line, "data:")
		if !ok {
			continue
		}
		data = strings.TrimSpace(data)
		if data == "" || data == "[DONE]" {
			continue
		}
		var envelope map[string]json.RawMessage
		if json.Unmarshal([]byte(data), &envelope) == nil && envelope["error"] != nil {
			return ChatResponse{}, responseError(http.StatusOK, []byte(data))
		}
		var chunk streamChunk
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			continue
		}
		if chunk.Usage != nil {
			result.PromptTokens, result.CompletionTokens = chunk.Usage.PromptTokens, chunk.Usage.CompletionTokens
		}
		if len(chunk.Choices) == 0 {
			continue
		}
		choice := chunk.Choices[0]
		if choice.FinishReason != "" {
			result.FinishReason = choice.FinishReason
		}
		if choice.Delta.ReasoningContent != "" && onDelta != nil {
			onDelta(choice.Delta.ReasoningContent)
		}
		if choice.Delta.Content != "" {
			content.WriteString(choice.Delta.Content)
			if onDelta != nil {
				onDelta(choice.Delta.Content)
			}
		}
		for _, delta := range choice.Delta.ToolCalls {
			call := calls[delta.Index]
			if call == nil {
				call = &ToolCall{Type: "function"}
				calls[delta.Index] = call
			}
			if delta.ID != "" {
				call.ID = delta.ID
			}
			if delta.Type != "" {
				call.Type = delta.Type
			}
			call.Function.Name += delta.Function.Name
			call.Function.Arguments += delta.Function.Arguments
		}
	}
	if err := scanner.Err(); err != nil {
		return ChatResponse{}, err
	}
	result.Content = content.String()
	for index := 0; index < len(calls); index++ {
		if call, ok := calls[index]; ok {
			result.ToolCalls = append(result.ToolCalls, *call)
		}
	}
	if result.Content == "" && len(result.ToolCalls) == 0 && result.FinishReason == "" {
		return ChatResponse{}, fmt.Errorf("model %s returned no choices", request.Model)
	}
	return result, nil
}
