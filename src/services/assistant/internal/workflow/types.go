package workflow

import (
	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/security"
)

const (
	NameConversationTurn   = "ConversationTurn"
	NameSubagentTask       = "SubagentTask"
	NameSecurityAssessment = "SecurityAssessment"
)

type RequestContext struct {
	SessionDate   string `json:"session_date,omitempty"`
	SessionIndex  *int   `json:"session_index,omitempty"`
	ExerciseIndex *int   `json:"exercise_index,omitempty"`
	TemplateSK    string `json:"template_sk,omitempty"`
	Area          string `json:"area,omitempty"`
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
	Kind             string               `json:"kind"`
	Model            string               `json:"model"`
	Task             string               `json:"task"`
	Message          string               `json:"message"`
	Identity         access.Identity      `json:"identity"`
	ConversationID   string               `json:"conversation_id"`
	Depth            int                  `json:"depth"`
	Context          RequestContext       `json:"context"`
	Signals          []string             `json:"signals"`
	HistoryGap       bool                 `json:"history_gap"`
	HistoryReference bool                 `json:"history_reference"`
	Floor            security.Verdict     `json:"floor"`
	Assessment       *security.Assessment `json:"assessment,omitempty"`
}

type SubagentOutput struct {
	Reply          string           `json:"reply"`
	UsedOperations []string         `json:"used_operations"`
	Proposals      []string         `json:"proposals"`
	Floor          security.Verdict `json:"floor"`
	Error          string           `json:"error,omitempty"`
}
