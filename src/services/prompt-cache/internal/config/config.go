package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Port            string
	ValkeyURL       string
	MCPURL          string
	DecisionsURL    string
	DecisionModel   string
	OpenAIKey       string
	DecisionTimeout time.Duration
	MinConfidence   float64
	EntryTTL        time.Duration
	SemanticTimeout time.Duration
	StoreTimeout    time.Duration
	CandidateLimit  int
}

func value(name, fallback string) string {
	if text := os.Getenv(name); text != "" {
		return text
	}
	return fallback
}

func number(name string, fallback int) int {
	parsed, err := strconv.Atoi(os.Getenv(name))
	if err != nil || parsed <= 0 {
		return fallback
	}
	return parsed
}

func confidence(name string, fallback float64) float64 {
	parsed, err := strconv.ParseFloat(os.Getenv(name), 64)
	if err != nil || parsed < 0 || parsed > 1 {
		return fallback
	}
	return parsed
}

func FromEnv() Config {
	return Config{
		Port:            strconv.Itoa(number("PORT", 8000)),
		ValkeyURL:       value("VALKEY_URL", "redis://pl-valkey:6379"),
		MCPURL:          value("PROMPT_CACHE_MCP_URL", "http://pl-prompt-cache-mcp:8000/mcp"),
		DecisionsURL:    strings.TrimSpace(value("DECISIONS_URL", "https://api.openai.com/v1/decisions")),
		DecisionModel:   value("DECISION_MODEL", "gpt-6-luna"),
		OpenAIKey:       strings.TrimSpace(os.Getenv("OPENAI_API_KEY")),
		DecisionTimeout: time.Duration(number("DECISION_TIMEOUT_MS", 3000)) * time.Millisecond,
		MinConfidence:   confidence("DECISION_MIN_CONFIDENCE", 0.8),
		EntryTTL:        time.Duration(number("ENTRY_TTL_SECONDS", 30*24*3600)) * time.Second,
		SemanticTimeout: time.Duration(number("SEMANTIC_TIMEOUT_MS", 4000)) * time.Millisecond,
		StoreTimeout:    time.Duration(number("STORE_TIMEOUT_MS", 10000)) * time.Millisecond,
		CandidateLimit:  number("CANDIDATE_LIMIT", 3),
	}
}
