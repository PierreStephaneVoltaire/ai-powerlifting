package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/pyjson"
)

const protocolVersion = "2025-03-26"

func rpcError(id any, code int, message string) map[string]any {
	return map[string]any{"jsonrpc": "2.0", "id": id, "error": map[string]any{"code": code, "message": message}}
}

func (a *API) tools() []any {
	tools := []any{}
	for _, operation := range a.Service.Registry.All() {
		if operation.InternalOnly {
			continue
		}
		tool := map[string]any{"name": operation.Name, "description": operation.Description, "inputSchema": operation.InputSchema}
		if operation.Execution == contract.ExecutionAI {
			tool["outputSchema"] = jobSubmitted
		} else if operation.ResultSchema["type"] == "object" {
			tool["outputSchema"] = operation.ResultSchema
		}
		tools = append(tools, tool)
	}
	return tools
}

func (a *API) mcp(ctx context.Context, raw []byte, caller auth.Caller) (int, any) {
	value, err := pyjson.Decode(raw)
	body, isObject := value.(map[string]any)
	if err != nil || !isObject {
		return http.StatusOK, rpcError(nil, -32700, "Parse error")
	}
	id, hasID := body["id"]
	if !hasID || id == nil {
		return http.StatusAccepted, map[string]any{}
	}
	var result map[string]any
	switch body["method"] {
	case "initialize":
		result = map[string]any{"protocolVersion": protocolVersion, "capabilities": map[string]any{"tools": map[string]any{}}, "serverInfo": map[string]any{"name": "powerlifting-" + a.Domain, "version": "1.0.0"}}
	case "ping":
		result = map[string]any{}
	case "tools/list":
		result = map[string]any{"tools": a.tools()}
	case "tools/call":
		result = a.callTool(ctx, body, caller)
	default:
		return http.StatusOK, rpcError(id, -32601, "Method not found")
	}
	return http.StatusOK, map[string]any{"jsonrpc": "2.0", "id": id, "result": result}
}

func (a *API) callTool(ctx context.Context, body map[string]any, caller auth.Caller) map[string]any {
	params, _ := body["params"].(map[string]any)
	name, _ := params["name"].(string)
	arguments, _ := params["arguments"].(map[string]any)
	if arguments == nil {
		arguments = map[string]any{}
	}
	response, err := a.Service.Call(ctx, name, arguments, auth.Caller{Person: caller.Person, Athlete: caller.Athlete, Source: caller.Source})
	if err != nil {
		var failure *apperr.Error
		if !errors.As(asError(err), &failure) {
			failure = apperr.Internal(err.Error())
		}
		text, _ := json.Marshal(map[string]any{"error": failure.Detail(), "status": failure.Status})
		return map[string]any{"content": []any{map[string]any{"type": "text", "text": string(text)}}, "isError": true}
	}
	text, _ := json.Marshal(response.Body)
	result := map[string]any{"content": []any{map[string]any{"type": "text", "text": string(text)}}, "isError": false}
	if structured, isObject := response.Body.(map[string]any); isObject {
		result["structuredContent"] = structured
	}
	return result
}
