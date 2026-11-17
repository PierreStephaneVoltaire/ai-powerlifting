package activities

import (
	"context"
	"regexp"

	"powerlifting/assistant/internal/security"
)

const MaxChars = 2000

var injectionPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|guardrails?|prompt)\b`),
	regexp.MustCompile(`(?i)\b(system|developer)\s+(prompt|message|instructions?)\b`),
	regexp.MustCompile(`(?i)\b(api[_ -]?key|token|password|secret|credentials?)\b`),
}

var signalPatterns = map[string]*regexp.Regexp{
	security.SignalDestructive:    regexp.MustCompile(`(?i)\b(delete|remove|wipe|erase|purge|overwrite|reset|clear)\b`),
	security.SignalBulkChange:     regexp.MustCompile(`(?i)\b(all|every|entire|whole)\b.{0,30}\b(sessions?|templates?|goals?|history|logs?|entries|data|weeks?|phases?)\b`),
	security.SignalOtherPerson:    regexp.MustCompile(`(?i)\b(someone else'?s?|other (athletes?|users?|people|person)|another (athlete|user|person)|everyone'?s?)\b`),
	security.SignalApprovalBypass: regexp.MustCompile(`(?i)\b(without|skip|bypass|no)\b.{0,20}\b(approval|confirm(ation)?|asking|review)\b|\bauto[- ]?(approve|commit)\b`),
}

var historyReference = regexp.MustCompile(`(?i)\b(earlier|before|previous(ly)?|last time|as (i|we) (said|discussed|agreed)|we (discussed|talked|agreed)|you (said|told|suggested|mentioned)|same as|again|like (that|before))\b`)

var refusals = map[string]string{
	"length":    "That message is too long for this chat; keep it under 2000 characters.",
	"rate":      "Too many messages at once; wait a minute and try again.",
	"injection": "I can't act on that. Ask about your training instead.",
}

type Rejection struct {
	Code  string
	Reply string
}

func CheckRules(message string) *Rejection {
	if len([]rune(message)) > MaxChars {
		return &Rejection{Code: "length", Reply: refusals["length"]}
	}
	for _, pattern := range injectionPatterns {
		if pattern.MatchString(message) {
			return &Rejection{Code: "injection", Reply: refusals["injection"]}
		}
	}
	return nil
}

func RateRejection() *Rejection {
	return &Rejection{Code: "rate", Reply: refusals["rate"]}
}

func Signals(message string) []string {
	var signals []string
	for _, name := range []string{security.SignalDestructive, security.SignalBulkChange, security.SignalOtherPerson, security.SignalApprovalBypass} {
		if signalPatterns[name].MatchString(message) {
			signals = append(signals, name)
		}
	}
	return signals
}

func HistoryReference(message string) bool {
	return historyReference.MatchString(message)
}

func (d *Deps) Guard(ctx context.Context, in GuardInput) (GuardOutput, error) {
	if rejection := CheckRules(in.Message); rejection != nil {
		return GuardOutput{Rejected: true, Code: rejection.Code, Reply: rejection.Reply}, nil
	}
	hits, err := d.Store.RateHit(ctx, in.Person, d.Now())
	if err != nil {
		return GuardOutput{}, err
	}
	if hits > d.Config.RatePerMinute {
		rejection := RateRejection()
		return GuardOutput{Rejected: true, Code: rejection.Code, Reply: rejection.Reply}, nil
	}
	return GuardOutput{Signals: Signals(in.Message), HistoryReference: HistoryReference(in.Message)}, nil
}
