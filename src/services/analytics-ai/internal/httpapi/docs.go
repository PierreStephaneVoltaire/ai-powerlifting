package httpapi

import (
	"encoding/json"

	"github.com/danielgtaylor/huma/v2"

	"powerlifting/analytics-ai/internal/contract"
)

func schemaOf(value map[string]any) *huma.Schema {
	raw, err := json.Marshal(value)
	if err == nil {
		var schema huma.Schema
		if json.Unmarshal(raw, &schema) == nil {
			return &schema
		}
	}
	return &huma.Schema{Type: "object", AdditionalProperties: true}
}

var jobSubmitted = map[string]any{
	"type": "object",
	"properties": map[string]any{
		"job_id":        map[string]any{"type": "string"},
		"generation_id": map[string]any{"type": "string"},
		"status":        map[string]any{"type": "string"},
	},
	"required": []any{"status"},
}

func patchDocumentation(documented huma.API, operations []*contract.Operation) {
	document := documented.OpenAPI()
	for _, operation := range operations {
		item := document.Paths["/operations/"+operation.Name]
		if item == nil || item.Post == nil {
			continue
		}
		post := item.Post
		post.RequestBody = &huma.RequestBody{Required: true, Content: map[string]*huma.MediaType{"application/json": {Schema: schemaOf(operation.InputSchema)}}}
		post.Responses = map[string]*huma.Response{
			"200": {Description: "Domain result, or the needs_inference / running challenge of a coach callback", Content: map[string]*huma.MediaType{"application/json": {Schema: schemaOf(operation.ResultSchema)}}},
			"4XX": {Description: "Rejected; body is {\"detail\": ...}", Content: map[string]*huma.MediaType{"application/json": {Schema: &huma.Schema{Type: "object"}}}},
		}
		post.Responses["202"] = &huma.Response{Description: "Report generation queued with the coach", Content: map[string]*huma.MediaType{"application/json": {Schema: schemaOf(jobSubmitted)}}}
	}
	for _, path := range []string{"/executions/{execution_id}", "/mcp"} {
		if item := document.Paths[path]; item != nil && item.Post != nil {
			item.Post.RequestBody = &huma.RequestBody{Required: true, Content: map[string]*huma.MediaType{"application/json": {Schema: &huma.Schema{Type: "object"}}}}
		}
	}
}
