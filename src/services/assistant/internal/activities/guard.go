package activities

import "regexp"

const MaxChars = 2000

var injectionPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|guardrails?|prompt)\b`),
	regexp.MustCompile(`(?i)\b(system|developer)\s+(prompt|message|instructions?)\b`),
	regexp.MustCompile(`(?i)\b(api[_ -]?key|token|password|secret|credentials?)\b`),
}

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
