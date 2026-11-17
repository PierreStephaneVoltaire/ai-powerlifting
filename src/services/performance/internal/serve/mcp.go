package serve

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/danielgtaylor/huma/v2"

	"powerlifting/performance/internal/apperr"
	"powerlifting/performance/internal/auth"
	"powerlifting/performance/internal/contract"
	"powerlifting/performance/internal/pyjson"
	"powerlifting/performance/internal/service"
)

const protocolVersion = "2025-03-26"

type rpcRequest struct {
	ID     json.RawMessage `json:"id"`
	Method string          `json:"method"`
	Params json.RawMessage `json:"params"`
}

type mcpCallInput struct {
	callInput
	Authorization string `header:"Authorization" required:"false" doc:"Bearer job token issued by the assistant."`
}

func registerMCP(api huma.API, svc *service.Service, verifier *auth.JobVerifier) {
	huma.Register(api, huma.Operation{
		OperationID:      "mcp",
		Method:           http.MethodPost,
		Path:             "/mcp",
		Summary:          "MCP JSON-RPC endpoint exposing the operations as tools",
		Tags:             []string{"mcp"},
		SkipValidateBody: true,
		Responses: map[string]*huma.Response{
			"200": {Description: "JSON-RPC response.", Content: map[string]*huma.MediaType{jsonType: {Schema: &huma.Schema{Type: "object"}}}},
		},
	}, func(ctx context.Context, input *mcpCallInput) (*rawOutput, error) {
		var request rpcRequest
		if err := json.Unmarshal(input.RawBody, &request); err != nil {
			return nil, apperr.Body()
		}
		if len(request.ID) == 0 || string(request.ID) == "null" {
			return encoded(http.StatusAccepted, map[string]any{})
		}
		caller, _, err := verifier.Resolve(auth.Presented{Authorization: input.Authorization, Person: input.PersonPk, Athlete: input.AthletePk, Source: input.SourcePrincipal}, request.Method, request.Params)
		if err != nil {
			return nil, &apperr.Error{Status: http.StatusUnauthorized, Code: "unauthorized", Message: "Job token rejected"}
		}
		result, known := rpcResult(ctx, svc, request, caller)
		if !known {
			return encoded(http.StatusOK, map[string]any{
				"jsonrpc": "2.0", "id": request.ID,
				"error": map[string]any{"code": -32601, "message": "Method not found"},
			})
		}
		return encoded(http.StatusOK, map[string]any{"jsonrpc": "2.0", "id": request.ID, "result": result})
	})
	documentBody(api, "/mcp", &huma.Schema{Type: "object"})
}

func rpcResult(ctx context.Context, svc *service.Service, request rpcRequest, caller auth.Caller) (any, bool) {
	switch request.Method {
	case "initialize":
		return map[string]any{
			"protocolVersion": protocolVersion,
			"capabilities":    map[string]any{"tools": map[string]any{}},
			"serverInfo":      map[string]any{"name": "powerlifting-" + contract.Domain, "version": "1.0.0"},
		}, true
	case "ping":
		return map[string]any{}, true
	case "tools/list":
		return map[string]any{"tools": tools(svc.Registry)}, true
	case "tools/call":
		return callTool(ctx, svc, request.Params, caller), true
	}
	return nil, false
}

func tools(registry *contract.Registry) []any {
	listed := []any{}
	for _, operation := range registry.All() {
		if operation.InternalOnly {
			continue
		}
		tool := map[string]any{
			"name":        operation.Name,
			"description": operation.Description,
			"inputSchema": operation.InputSchema,
		}
		if operation.ResultSchema["type"] == "object" {
			tool["outputSchema"] = operation.ResultSchema
		}
		listed = append(listed, tool)
	}
	return listed
}

func callTool(ctx context.Context, svc *service.Service, raw json.RawMessage, caller auth.Caller) map[string]any {
	var params struct {
		Name      string          `json:"name"`
		Arguments json.RawMessage `json:"arguments"`
	}
	_ = json.Unmarshal(raw, &params)
	arguments := map[string]any{}
	var failure *apperr.Error
	if len(params.Arguments) > 0 && string(params.Arguments) != "null" {
		parsed, err := objectBody(params.Arguments)
		if err != nil {
			failure = toError(err)
		} else {
			arguments = parsed
		}
	}
	var result any
	if failure == nil {
		var err error
		if result, err = svc.Call(ctx, params.Name, arguments, caller); err != nil {
			failure = toError(err)
		}
	}
	if failure != nil {
		return map[string]any{
			"content": []any{map[string]any{"type": "text", "text": marshal(map[string]any{"error": failure.Detail(), "status": failure.Status})}},
			"isError": true,
		}
	}
	reply := map[string]any{
		"content": []any{map[string]any{"type": "text", "text": marshal(result)}},
		"isError": false,
	}
	if object, ok := result.(map[string]any); ok {
		reply["structuredContent"] = object
	}
	return reply
}

func toError(err error) *apperr.Error {
	if typed, ok := asStatusError(err).(*apperr.Error); ok {
		return typed
	}
	return apperr.Internal(err.Error())
}

func marshal(value any) string {
	encoded, _ := pyjson.Encode(value)
	return string(encoded)
}
