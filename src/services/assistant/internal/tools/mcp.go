package tools

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	protocolVersion = "2025-06-18"
	callTimeout     = 120 * time.Second
	maxResponse     = 8 << 20
)

type Tool struct {
	Name        string          `json:"name"`
	Alias       string          `json:"alias"`
	Namespaced  string          `json:"namespaced"`
	Description string          `json:"description"`
	InputSchema json.RawMessage `json:"input_schema"`
}

type CallResult struct {
	Text    string `json:"text"`
	IsError bool   `json:"is_error"`
}

type MCPClient struct {
	URL       string
	APIKey    string
	Aliases   []string
	Separator string
	HTTP      *http.Client

	mu      sync.RWMutex
	byName  map[string]string
	counter int64
}

func NewMCPClient(url, apiKey string, aliases []string, separator string) *MCPClient {
	sorted := append([]string(nil), aliases...)
	sort.Slice(sorted, func(i, j int) bool { return len(sorted[i]) > len(sorted[j]) })
	return &MCPClient{URL: url, APIKey: apiKey, Aliases: sorted, Separator: separator, HTTP: &http.Client{Timeout: callTimeout}, byName: map[string]string{}}
}

func (c *MCPClient) Split(namespaced string) (alias, name string, ok bool) {
	for _, candidate := range c.Aliases {
		prefix := candidate + c.Separator
		if strings.HasPrefix(namespaced, prefix) {
			return candidate, strings.TrimPrefix(namespaced, prefix), true
		}
	}
	return "", "", false
}

func (c *MCPClient) headers(jobToken string) http.Header {
	header := http.Header{}
	header.Set("Content-Type", "application/json")
	header.Set("Accept", "application/json, text/event-stream")
	header.Set("Authorization", "Bearer "+c.APIKey)
	header.Set("x-litellm-api-key", "Bearer "+c.APIKey)
	header.Set("x-mcp-servers", strings.Join(c.Aliases, ","))
	for _, alias := range c.Aliases {
		header.Set("x-mcp-"+alias+"-authorization", "Bearer "+jobToken)
	}
	return header
}

type rpcResponse struct {
	ID     json.RawMessage `json:"id"`
	Result json.RawMessage `json:"result"`
	Error  *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

func (c *MCPClient) post(ctx context.Context, jobToken, session string, payload map[string]any, wantID int64) (rpcResponse, string, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return rpcResponse{}, "", err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.URL, bytes.NewReader(body))
	if err != nil {
		return rpcResponse{}, "", err
	}
	request.Header = c.headers(jobToken)
	if session != "" {
		request.Header.Set("Mcp-Session-Id", session)
		request.Header.Set("MCP-Protocol-Version", protocolVersion)
	}
	response, err := c.HTTP.Do(request)
	if err != nil {
		return rpcResponse{}, "", err
	}
	defer response.Body.Close()
	newSession := response.Header.Get("Mcp-Session-Id")
	if response.StatusCode == http.StatusAccepted || wantID == 0 {
		io.Copy(io.Discard, io.LimitReader(response.Body, maxResponse))
		if response.StatusCode >= 400 {
			return rpcResponse{}, newSession, fmt.Errorf("mcp gateway returned %d", response.StatusCode)
		}
		return rpcResponse{}, newSession, nil
	}
	if response.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 2048))
		return rpcResponse{}, newSession, fmt.Errorf("mcp gateway returned %d: %.200s", response.StatusCode, raw)
	}
	parsed, err := readRPC(response, wantID)
	return parsed, newSession, err
}

func readRPC(response *http.Response, wantID int64) (rpcResponse, error) {
	want := fmt.Sprint(wantID)
	if strings.HasPrefix(response.Header.Get("Content-Type"), "text/event-stream") {
		scanner := bufio.NewScanner(response.Body)
		scanner.Buffer(make([]byte, 0, 64*1024), maxResponse)
		for scanner.Scan() {
			line := scanner.Text()
			if !strings.HasPrefix(line, "data:") {
				continue
			}
			var message rpcResponse
			if json.Unmarshal([]byte(strings.TrimSpace(strings.TrimPrefix(line, "data:"))), &message) != nil {
				continue
			}
			if string(message.ID) == want {
				return message, nil
			}
		}
		if err := scanner.Err(); err != nil {
			return rpcResponse{}, err
		}
		return rpcResponse{}, errors.New("mcp stream ended without a response")
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, maxResponse))
	if err != nil {
		return rpcResponse{}, err
	}
	var message rpcResponse
	if err := json.Unmarshal(raw, &message); err != nil {
		return rpcResponse{}, err
	}
	return message, nil
}

func (c *MCPClient) nextID() int64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.counter++
	return c.counter
}

func (c *MCPClient) request(ctx context.Context, jobToken, method string, params map[string]any) (json.RawMessage, error) {
	initID := c.nextID()
	_, session, err := c.post(ctx, jobToken, "", map[string]any{
		"jsonrpc": "2.0", "id": initID, "method": "initialize",
		"params": map[string]any{"protocolVersion": protocolVersion, "capabilities": map[string]any{}, "clientInfo": map[string]any{"name": "pl-assistant", "version": "1.0.0"}},
	}, initID)
	if err != nil {
		return nil, err
	}
	if _, _, err := c.post(ctx, jobToken, session, map[string]any{"jsonrpc": "2.0", "method": "notifications/initialized"}, 0); err != nil {
		return nil, err
	}
	id := c.nextID()
	message, _, err := c.post(ctx, jobToken, session, map[string]any{"jsonrpc": "2.0", "id": id, "method": method, "params": params}, id)
	if err != nil {
		return nil, err
	}
	if message.Error != nil {
		return nil, fmt.Errorf("mcp %s failed: %s", method, message.Error.Message)
	}
	return message.Result, nil
}

func (c *MCPClient) List(ctx context.Context, jobToken string) ([]Tool, error) {
	raw, err := c.request(ctx, jobToken, "tools/list", map[string]any{})
	if err != nil {
		return nil, err
	}
	var payload struct {
		Tools []struct {
			Name        string          `json:"name"`
			Description string          `json:"description"`
			InputSchema json.RawMessage `json:"inputSchema"`
		} `json:"tools"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, err
	}
	listed := make([]Tool, 0, len(payload.Tools))
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, item := range payload.Tools {
		alias, name, ok := c.Split(item.Name)
		if !ok {
			continue
		}
		c.byName[name] = item.Name
		listed = append(listed, Tool{Name: name, Alias: alias, Namespaced: item.Name, Description: item.Description, InputSchema: item.InputSchema})
	}
	return listed, nil
}

func (c *MCPClient) namespaced(ctx context.Context, jobToken, name string) (string, error) {
	c.mu.RLock()
	found := c.byName[name]
	c.mu.RUnlock()
	if found != "" {
		return found, nil
	}
	if _, err := c.List(ctx, jobToken); err != nil {
		return "", err
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if found = c.byName[name]; found == "" {
		return "", fmt.Errorf("tool %s is not exposed by the gateway", name)
	}
	return found, nil
}

func (c *MCPClient) Call(ctx context.Context, jobToken, name string, arguments map[string]any) (CallResult, error) {
	namespaced, err := c.namespaced(ctx, jobToken, name)
	if err != nil {
		return CallResult{}, err
	}
	raw, err := c.request(ctx, jobToken, "tools/call", map[string]any{"name": namespaced, "arguments": arguments})
	if err != nil {
		return CallResult{}, err
	}
	var payload struct {
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
		IsError bool `json:"isError"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return CallResult{}, err
	}
	var text []string
	for _, part := range payload.Content {
		if part.Type == "text" {
			text = append(text, part.Text)
		}
	}
	return CallResult{Text: strings.Join(text, "\n"), IsError: payload.IsError}, nil
}

var versionKeys = []string{"version", "_version", "etag", "updated_at", "version_sk"}

func Version(raw string) string {
	var object map[string]any
	if json.Unmarshal([]byte(raw), &object) == nil {
		for _, key := range versionKeys {
			if value, ok := object[key]; ok && value != nil {
				return fmt.Sprint(value)
			}
		}
	}
	sum := sha256.Sum256([]byte(raw))
	return "sha256:" + hex.EncodeToString(sum[:])
}
