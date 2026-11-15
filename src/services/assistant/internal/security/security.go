package security

import (
	"encoding/json"
	"slices"
)

type Verdict string

const (
	Allow           Verdict = "allow"
	RequireApproval Verdict = "require_approval"
	Block           Verdict = "block"
)

const (
	TriggerGuardSignal      = "guard_signal"
	TriggerOrchestratorFlag = "orchestrator_flag"
	TriggerDestructive      = "destructive_proposal"
	TriggerHistoryGap       = "history_gap_mutation"
)

const (
	SignalDestructive    = "destructive_language"
	SignalBulkChange     = "bulk_change"
	SignalOtherPerson    = "other_person_reference"
	SignalApprovalBypass = "approval_bypass"
)

type Assessment struct {
	Verdict  Verdict  `json:"verdict"`
	Risk     string   `json:"risk"`
	Reasons  []string `json:"reasons"`
	Triggers []string `json:"triggers"`
	Source   string   `json:"source"`
}

func rank(verdict Verdict) int {
	switch verdict {
	case Block:
		return 2
	case RequireApproval:
		return 1
	}
	return 0
}

func Tighten(current, proposed Verdict) Verdict {
	if rank(proposed) > rank(current) {
		return proposed
	}
	if rank(current) == 0 && current != Allow {
		return Allow
	}
	return current
}

func Floor(triggers []string) Verdict {
	if slices.Contains(triggers, TriggerDestructive) || slices.Contains(triggers, TriggerHistoryGap) {
		return RequireApproval
	}
	return Allow
}

func GuardTriggers(signals []string) bool {
	if slices.Contains(signals, SignalOtherPerson) || slices.Contains(signals, SignalApprovalBypass) {
		return true
	}
	return slices.Contains(signals, SignalBulkChange) && slices.Contains(signals, SignalDestructive)
}

type TriggerInput struct {
	Signals           []string
	Flagged           bool
	DestructiveChange bool
	HistoryGap        bool
	Mutation          bool
}

func Triggers(input TriggerInput) []string {
	var triggers []string
	if GuardTriggers(input.Signals) {
		triggers = append(triggers, TriggerGuardSignal)
	}
	if input.Flagged {
		triggers = append(triggers, TriggerOrchestratorFlag)
	}
	if input.Mutation && input.DestructiveChange {
		triggers = append(triggers, TriggerDestructive)
	}
	if input.Mutation && input.HistoryGap {
		triggers = append(triggers, TriggerHistoryGap)
	}
	return triggers
}

type raw struct {
	Verdict string   `json:"verdict"`
	Risk    string   `json:"risk"`
	Reasons []string `json:"reasons"`
}

func Fallback(triggers []string, reason string) Assessment {
	return Assessment{Verdict: Tighten(RequireApproval, Floor(triggers)), Risk: "unknown", Reasons: []string{reason}, Triggers: triggers, Source: "fallback"}
}

func Parse(content string, triggers []string) Assessment {
	var parsed raw
	if err := json.Unmarshal([]byte(content), &parsed); err != nil {
		return Fallback(triggers, "assessment output was malformed")
	}
	verdict := Verdict(parsed.Verdict)
	if verdict != Allow && verdict != RequireApproval && verdict != Block {
		return Fallback(triggers, "assessment verdict was not recognised")
	}
	return Assessment{Verdict: Tighten(Floor(triggers), verdict), Risk: parsed.Risk, Reasons: parsed.Reasons, Triggers: triggers, Source: "model"}
}

func Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"verdict": map[string]any{"type": "string", "enum": []string{string(Allow), string(RequireApproval), string(Block)}},
			"risk":    map[string]any{"type": "string", "enum": []string{"low", "medium", "high"}},
			"reasons": map[string]any{"type": "array", "items": map[string]any{"type": "string"}},
		},
		"required":             []string{"verdict", "risk", "reasons"},
		"additionalProperties": false,
	}
}
