package decision

import (
	"context"
	"encoding/json"

	"powerlifting/prompt-cache/internal/entry"
)

const (
	Same       = "same"
	Contextual = "contextual"
	Temporal   = "temporal"
	None       = "none"
)

type Candidate struct {
	EntryID  string          `json:"entry_id"`
	Request  json.RawMessage `json:"request"`
	Response json.RawMessage `json:"response"`
	Context  entry.Context   `json:"context"`
}

type Input struct {
	Athlete    string
	Operation  string
	Request    json.RawMessage
	Context    entry.Context
	Candidates []Candidate
}

type Verdict struct {
	EntryID    string  `json:"entry_id,omitempty"`
	Reason     string  `json:"reason"`
	Confidence float64 `json:"confidence,omitempty"`
}

type Decider interface {
	Decide(ctx context.Context, input Input) (Verdict, error)
}

type Miss struct{}

func (Miss) Decide(context.Context, Input) (Verdict, error) {
	return Verdict{Reason: None}, nil
}
