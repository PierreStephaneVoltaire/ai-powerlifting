package domainjobs

import (
	"context"
	"encoding/json"
	"maps"
	"net/http"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
)

const ActivityName = "DomainJobStep"

type Payload struct {
	Operation         string          `json:"operation"`
	Domain            string          `json:"domain"`
	Athlete           string          `json:"athlete"`
	Arguments         map[string]any  `json:"arguments"`
	GenerationID      string          `json:"generation_id,omitempty"`
	GenerationAttempt int             `json:"generation_attempt,omitempty"`
	Access            json.RawMessage `json:"access_requirements,omitempty"`
}

func (p Payload) AccessArguments() map[string]any {
	arguments := make(map[string]any, len(p.Arguments)+3)
	maps.Copy(arguments, p.Arguments)
	if p.Operation == "import_parse_file" {
		delete(arguments, "base64_content")
	}
	return arguments
}

type Service struct {
	Store      *store.Store
	Access     *access.Client
	Catalog    map[string]Operation
	Models     map[string]Model
	ServiceURL string
	HTTP       *http.Client
	Chat       func(context.Context, llm.ChatRequest) (llm.ChatResponse, error)
	Lifetime   func(context.Context, string) (string, error)
}

type StepInput struct {
	ID       string `json:"id"`
	Sequence int    `json:"sequence"`
	Kind     string `json:"kind"`
}

type StepOutput struct {
	Status string `json:"status"`
	Next   string `json:"next,omitempty"`
}

type continuation struct {
	Status         string          `json:"status"`
	ExecutionID    string          `json:"execution_id"`
	ChallengeID    string          `json:"challenge_id"`
	Messages       []llm.Message   `json:"messages"`
	Tools          []llm.ToolDef   `json:"tools"`
	ResponseFormat json.RawMessage `json:"response_format"`
	Result         json.RawMessage `json:"result"`
}

type answered struct {
	ExecutionID string          `json:"execution_id"`
	ChallengeID string          `json:"challenge_id"`
	Content     json.RawMessage `json:"content"`
}

func Terminal(status string) bool {
	switch status {
	case "succeeded", "failed", "cancelled", "uncertain":
		return true
	default:
		return false
	}
}

func marshal(value any) json.RawMessage {
	raw, _ := json.Marshal(value)
	return raw
}
