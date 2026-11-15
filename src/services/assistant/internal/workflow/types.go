package workflow

import (
	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/llm"
)

const (
	NameConversationTurn = "ConversationTurn"
	NameSubagentTask     = "SubagentTask"
)

type RequestContext struct {
	SessionDate   string `json:"session_date,omitempty"`
	SessionIndex  *int   `json:"session_index,omitempty"`
	ExerciseIndex *int   `json:"exercise_index,omitempty"`
	TemplateSK    string `json:"template_sk,omitempty"`
}

type TurnInput struct {
	TurnID         string         `json:"turn_id"`
	ConversationID string         `json:"conversation_id"`
	Person         string         `json:"person"`
	Athlete        string         `json:"athlete"`
	Surface        string         `json:"surface"`
	Messages       []llm.Message  `json:"messages"`
	Context        RequestContext `json:"context"`
}

type TurnOutput struct {
	Status    string   `json:"status"`
	Reply     string   `json:"reply"`
	Error     string   `json:"error,omitempty"`
	Proposals []string `json:"proposals,omitempty"`
}

type SubagentInput struct {
	Kind                string          `json:"kind"`
	Task                string          `json:"task"`
	Identity            access.Identity `json:"identity"`
	ConversationID      string          `json:"conversation_id"`
	Depth               int             `json:"depth"`
	Context             RequestContext  `json:"context"`
	ForceDestructive    bool            `json:"force_destructive"`
	UnrelatedHistorical bool            `json:"unrelated_historical"`
	DestructiveIntent   bool            `json:"destructive_intent"`
}

type SubagentOutput struct {
	Reply          string   `json:"reply"`
	UsedOperations []string `json:"used_operations"`
	Proposals      []string `json:"proposals"`
	Error          string   `json:"error,omitempty"`
}
