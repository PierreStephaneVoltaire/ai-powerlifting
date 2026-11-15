package activities

import (
	"encoding/json"
	"time"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/agent"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/tools"
)

const (
	NameResolveIdentity = "ResolveIdentity"
	NameMintToken       = "MintToken"
	NameGuard           = "Guard"
	NameDecide          = "Decide"
	NameRetrieve        = "Retrieve"
	NameListTools       = "ListTools"
	NameModelCall       = "ModelCall"
	NameToolCall        = "ToolCall"
	NamePropose         = "Propose"
	NameExpireProposal  = "ExpireProposal"
	NameCommit          = "Commit"
	NameDeliver         = "Deliver"
)

type Subject struct {
	Person         string   `json:"person"`
	Athlete        string   `json:"athlete"`
	ConversationID string   `json:"conversation_id"`
	WorkflowID     string   `json:"workflow_id"`
	Scope          []string `json:"scope"`
}

type ResolveInput struct {
	TurnID         string `json:"turn_id"`
	Person         string `json:"person"`
	Athlete        string `json:"athlete"`
	ConversationID string `json:"conversation_id"`
	WorkflowID     string `json:"workflow_id"`
}

type ResolveOutput struct {
	Allowed  bool            `json:"allowed"`
	Reason   string          `json:"reason"`
	Identity access.Identity `json:"identity"`
}

type MintInput struct {
	Identity       access.Identity `json:"identity"`
	Surface        string          `json:"surface"`
	ConversationID string          `json:"conversation_id"`
	WorkflowID     string          `json:"workflow_id"`
}

type MintOutput struct {
	Subject   Subject   `json:"subject"`
	ExpiresAt time.Time `json:"expires_at"`
}

type GuardInput struct {
	Person  string `json:"person"`
	Message string `json:"message"`
}

type GuardOutput struct {
	Rejected bool   `json:"rejected"`
	Code     string `json:"code"`
	Reply    string `json:"reply"`
}

type DecideInput struct {
	Message          string `json:"message"`
	RequestedSurface string `json:"requested_surface"`
}

type Decision struct {
	Surface             string `json:"surface"`
	UnrelatedHistorical bool   `json:"unrelated_historical_change"`
	DestructiveIntent   bool   `json:"destructive_intent"`
	Reason              string `json:"reason"`
	Fallback            bool   `json:"fallback"`
}

type RetrieveInput struct {
	Identity access.Identity `json:"identity"`
	Query    string          `json:"query"`
}

type RetrieveOutput struct {
	Snippets []store.Snippet `json:"snippets"`
}

type ListToolsInput struct {
	Subject Subject `json:"subject"`
}

type ListToolsOutput struct {
	Tools []tools.Tool `json:"tools"`
}

type ModelCallInput struct {
	Model     string        `json:"model"`
	Messages  []llm.Message `json:"messages"`
	Tools     []llm.ToolDef `json:"tools"`
	MaxTokens int           `json:"max_tokens"`
}

type ToolCallInput struct {
	Subject       Subject        `json:"subject"`
	Name          string         `json:"name"`
	Arguments     map[string]any `json:"arguments"`
	AllowMutation bool           `json:"allow_mutation"`
}

type ToolCallOutput struct {
	Text    string `json:"text"`
	IsError bool   `json:"is_error"`
	Denied  bool   `json:"denied"`
	JTI     string `json:"jti"`
}

type ProposeInput struct {
	ID               string                `json:"id"`
	TurnID           string                `json:"turn_id"`
	Subject          Subject               `json:"subject"`
	Request          agent.ProposalRequest `json:"request"`
	ForceDestructive bool                  `json:"force_destructive"`
}

type ProposalView struct {
	ID          string          `json:"id"`
	Operation   string          `json:"operation"`
	Summary     string          `json:"summary"`
	TargetID    string          `json:"target_id"`
	Destructive bool            `json:"destructive"`
	State       store.State     `json:"state"`
	Diff        json.RawMessage `json:"diff,omitempty"`
	Error       string          `json:"error,omitempty"`
}

type ExpireInput struct {
	ID string `json:"id"`
}

type CommitInput struct {
	ProposalID string `json:"proposal_id"`
}

type CommitOutput struct {
	Outcome string `json:"outcome"`
	Text    string `json:"text"`
}

type DeliverInput struct {
	TurnID         string   `json:"turn_id"`
	ConversationID string   `json:"conversation_id"`
	Athlete        string   `json:"athlete"`
	Request        string   `json:"request"`
	Status         string   `json:"status"`
	Reply          string   `json:"reply"`
	Error          string   `json:"error"`
	UsedOperations []string `json:"used_operations"`
}

type ApprovalEvent struct {
	Approve  bool   `json:"approve"`
	Approver string `json:"approver"`
}

func ApprovalEventName(proposalID string) string {
	return "proposal-" + proposalID
}
