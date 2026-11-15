package agent

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/tools"
)

const (
	DelegateTool = "delegate_subagent"
	ProposeTool  = "propose_change"
	MaxToolText  = 12000
)

var ErrBudget = errors.New("agent budget exhausted")

type Limits struct {
	MaxSteps  int
	MaxTokens int
}

type State struct {
	Messages []llm.Message `json:"messages"`
	Steps    int           `json:"steps"`
	Tokens   int           `json:"tokens"`
}

func (s *State) Exhausted(limits Limits) error {
	if s.Steps >= limits.MaxSteps || s.Tokens >= limits.MaxTokens {
		return ErrBudget
	}
	return nil
}

func (s *State) Record(response llm.ChatResponse) {
	s.Steps++
	s.Tokens += response.PromptTokens + response.CompletionTokens
	s.Messages = append(s.Messages, llm.Message{Role: "assistant", Content: response.Content, ToolCalls: response.ToolCalls})
}

func (s *State) AddToolResult(callID, text string) {
	s.Messages = append(s.Messages, llm.Message{Role: "tool", ToolCallID: callID, Content: Truncate(text, MaxToolText)})
}

func Truncate(text string, limit int) string {
	if len(text) <= limit {
		return text
	}
	return text[:limit] + "\n[truncated]"
}

type CallKind string

const (
	KindTool     CallKind = "tool"
	KindDelegate CallKind = "delegate"
	KindPropose  CallKind = "propose"
)

type Call struct {
	ID        string
	Kind      CallKind
	Name      string
	Arguments map[string]any
	Malformed string
}

func Classify(call llm.ToolCall) Call {
	parsed := Call{ID: call.ID, Name: call.Function.Name, Kind: KindTool, Arguments: map[string]any{}}
	if strings.TrimSpace(call.Function.Arguments) != "" {
		if err := json.Unmarshal([]byte(call.Function.Arguments), &parsed.Arguments); err != nil {
			parsed.Malformed = "arguments are not a JSON object"
		}
	}
	switch call.Function.Name {
	case DelegateTool:
		parsed.Kind = KindDelegate
	case ProposeTool:
		parsed.Kind = KindPropose
	}
	return parsed
}

type Delegation struct {
	Kind string
	Task string
}

func ParseDelegation(arguments map[string]any) (Delegation, error) {
	kind, _ := arguments["kind"].(string)
	task, _ := arguments["task"].(string)
	if kind == "" || strings.TrimSpace(task) == "" {
		return Delegation{}, errors.New("kind and task are required")
	}
	return Delegation{Kind: kind, Task: task}, nil
}

type ProposalRequest struct {
	Operation       string         `json:"operation"`
	Arguments       map[string]any `json:"arguments"`
	Summary         string         `json:"summary"`
	TargetID        string         `json:"target_id"`
	ReadOperation   string         `json:"read_operation"`
	ReadArguments   map[string]any `json:"read_arguments"`
	DestructiveHint bool           `json:"destructive"`
}

func ParseProposal(arguments map[string]any) (ProposalRequest, error) {
	raw, err := json.Marshal(arguments)
	if err != nil {
		return ProposalRequest{}, err
	}
	var request ProposalRequest
	if err := json.Unmarshal(raw, &request); err != nil {
		return ProposalRequest{}, err
	}
	switch {
	case request.Operation == "":
		return ProposalRequest{}, errors.New("operation is required")
	case request.TargetID == "":
		return ProposalRequest{}, errors.New("target_id is required")
	case request.ReadOperation == "":
		return ProposalRequest{}, errors.New("read_operation is required to capture the target version")
	}
	if request.Arguments == nil {
		request.Arguments = map[string]any{}
	}
	if request.ReadArguments == nil {
		request.ReadArguments = map[string]any{}
	}
	return request, nil
}

func PseudoTools(surface tools.Surface, depth, maxDepth int) []llm.ToolDef {
	var defs []llm.ToolDef
	if depth < maxDepth && len(surface.Delegates) > 0 {
		kinds, _ := json.Marshal(surface.Delegates)
		defs = append(defs, llm.ToolDef{Type: "function", Function: llm.FunctionDef{
			Name:        DelegateTool,
			Description: "Hand a self-contained task to a specialist subagent and receive its answer. The subagent has its own restricted tools.",
			Parameters:  json.RawMessage(fmt.Sprintf(`{"type":"object","properties":{"kind":{"type":"string","enum":%s},"task":{"type":"string"}},"required":["kind","task"],"additionalProperties":false}`, kinds)),
		}})
	}
	if len(surface.Writes) > 0 {
		writes, _ := json.Marshal(surface.Writes)
		defs = append(defs, llm.ToolDef{Type: "function", Function: llm.FunctionDef{
			Name:        ProposeTool,
			Description: "Propose a change for the Person to approve. Nothing is written until they approve. Give the exact write operation and arguments, the id of the object changed, and a read operation that returns that object so its version is captured.",
			Parameters:  json.RawMessage(fmt.Sprintf(`{"type":"object","properties":{"operation":{"type":"string","enum":%s},"arguments":{"type":"object"},"summary":{"type":"string"},"target_id":{"type":"string"},"read_operation":{"type":"string"},"read_arguments":{"type":"object"},"destructive":{"type":"boolean"}},"required":["operation","arguments","summary","target_id","read_operation"],"additionalProperties":false}`, writes)),
		}})
	}
	return defs
}

func ToolDefs(listed []tools.Tool, surface tools.Surface, scope []string) []llm.ToolDef {
	allowed := map[string]bool{}
	for _, name := range scope {
		allowed[name] = true
	}
	var defs []llm.ToolDef
	for _, tool := range listed {
		if !allowed[tool.Name] || tools.IsMutating(tool.Name) {
			continue
		}
		schema := tool.InputSchema
		if len(schema) == 0 {
			schema = json.RawMessage(`{"type":"object","properties":{}}`)
		}
		defs = append(defs, llm.ToolDef{Type: "function", Function: llm.FunctionDef{Name: tool.Name, Description: tool.Description, Parameters: schema}})
	}
	return defs
}
