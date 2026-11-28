package domainjobs

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"powerlifting/assistant/internal/llm"
)

const inlineCharacters = 1048576 * 85 / 100
const chunkCharacters = 64000

var readInput = llm.ToolDef{Type: "function", Function: llm.FunctionDef{
	Name: "read_job_input", Description: "Read the next chunk of the current job's input.",
	Parameters: json.RawMessage(`{"type":"object","properties":{"offset":{"type":"integer","minimum":0}},"required":["offset"]}`),
}}

func answerSchema(challenge continuation) json.RawMessage {
	if len(challenge.Tools) != 0 {
		return challenge.Tools[0].Function.Parameters
	}
	var format struct {
		JSONSchema struct {
			Schema json.RawMessage `json:"schema"`
		} `json:"json_schema"`
	}
	_ = json.Unmarshal(challenge.ResponseFormat, &format)
	return format.JSONSchema.Schema
}

func completionText(text string) string {
	text = strings.TrimSpace(text)
	if strings.HasPrefix(text, "```") && strings.HasSuffix(text, "```") {
		if newline := strings.IndexByte(text, '\n'); newline >= 0 && newline < len(text)-3 {
			return strings.TrimSpace(text[newline+1 : len(text)-3])
		}
	}
	return text
}

func (s *Service) infer(ctx context.Context, settings Model, jobID, person string, challenge continuation, report string) (json.RawMessage, error) {
	var system, prompt []string
	for _, message := range challenge.Messages {
		switch message.Role {
		case "system", "developer":
			system = append(system, message.Content)
		default:
			prompt = append(prompt, "["+message.Role+"]\n"+message.Content)
		}
	}
	if report != "" {
		prompt = append(prompt, "Lifetime training report for reference:\n"+report)
	}
	source := strings.Join(prompt, "\n\n")
	rawSchema := answerSchema(challenge)
	var schema *jsonschema.Schema
	if len(rawSchema) != 0 && string(rawSchema) != "null" {
		var err error
		schema, err = compileSchema(rawSchema)
		if err != nil {
			return nil, errors.New("domain supplied an invalid response schema")
		}
		system = append(system, "Reply with exactly one JSON object matching this JSON Schema:\n"+string(rawSchema))
	}
	request := llm.ChatRequest{
		Model: settings.Model, ReasoningEffort: settings.Effort,
		Meta:     llm.Metadata{Role: "domain-job", WorkflowID: jobID, UserID: person},
		Messages: []llm.Message{{Role: "system", Content: strings.Join(system, "\n\n")}},
	}
	var input []rune
	offset := 0
	if len(source) >= inlineCharacters {
		input = []rune(source)
	}
	if len(input) >= inlineCharacters {
		request.Tools = []llm.ToolDef{readInput}
		request.Messages = append(request.Messages, llm.Message{Role: "user", Content: "Read the full job input with read_job_input, starting at offset 0 and following next_offset until it is null. Then complete the task."})
	} else {
		input = nil
		request.Messages = append(request.Messages, llm.Message{Role: "user", Content: source})
	}
	for attempts := 0; attempts < 3; {
		response, err := s.Chat(ctx, request)
		if err != nil {
			return nil, fmt.Errorf("LiteLLM inference failed: %w", err)
		}
		if len(response.ToolCalls) == 1 && offset < len(input) {
			call := response.ToolCalls[0]
			var arg struct {
				Offset *int `json:"offset"`
			}
			if call.Function.Name == readInput.Function.Name && json.Unmarshal([]byte(call.Function.Arguments), &arg) == nil && arg.Offset != nil && *arg.Offset == offset {
				end := min(offset+chunkCharacters, len(input))
				part := map[string]any{"text": string(input[offset:end]), "next_offset": nil}
				if end < len(input) {
					part["next_offset"] = end
				}
				offset = end
				request.Messages = append(request.Messages,
					llm.Message{Role: "assistant", Content: response.Content, ToolCalls: response.ToolCalls, ReasoningDetails: response.ReasoningDetails},
					llm.Message{Role: "tool", ToolCallID: call.ID, Content: string(marshal(part))},
				)
				if offset == len(input) {
					request.Tools = nil
				}
				continue
			}
		}
		attempts++
		if offset < len(input) {
			request.Messages = append(request.Messages, llm.Message{Role: "user", Content: fmt.Sprintf("Continue reading the job input from offset %d before answering.", offset)})
			continue
		}
		if schema == nil && response.Content != "" && response.FinishReason != "length" {
			return marshal(response.Content), nil
		}
		if schema != nil && response.FinishReason != "length" {
			candidate := completionText(response.Content)
			value, err := jsonschema.UnmarshalJSON(strings.NewReader(candidate))
			if err == nil && schema.Validate(value) == nil {
				return json.RawMessage(candidate), nil
			}
		}
		request.Messages = append(request.Messages,
			llm.Message{Role: "assistant", Content: response.Content},
			llm.Message{Role: "user", Content: "The previous answer did not validate. Return a complete answer in the requested format."},
		)
	}
	return nil, errors.New("model did not produce a valid domain response")
}
