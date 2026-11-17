package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	HTTPAddr         string
	LogLevel         string
	ProfileURL       string
	AllowedCallers   []string
	DaprGRPCEndpoint string
	LiteLLMBaseURL   string
	LiteLLMAPIKey    string
	MCPURL           string
	MCPAliases       []string
	MCPSeparator     string
	PrivateKeyPEM    string
	TokenTTL         time.Duration
	PGHost           string
	PGPort           string
	PGDatabase       string
	PGUser           string
	PGPassword       string
	PGSSLMode        string
	EmbedDim         int
	MaxConcurrency   int
	MaxSteps         int
	MaxTokens        int
	MaxDepth         int
	DelegationBudget int
	ApprovalTimeout  time.Duration
	RatePerMinute    int
	CoordinatorModel string
	StrongModel      string
	WebModel         string
	FastModel        string
	SecurityModel    string
	EmbedModel       string
	SubagentModels   map[string]string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func number(name string, fallback int) int {
	value, err := strconv.Atoi(env(name, ""))
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func list(name, fallback string) []string {
	var out []string
	for _, part := range strings.Split(env(name, fallback), ",") {
		if trimmed := strings.TrimSpace(part); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func daprEndpoint() string {
	if endpoint := env("DAPR_GRPC_ENDPOINT", ""); endpoint != "" {
		return endpoint
	}
	return "127.0.0.1:" + env("DAPR_GRPC_PORT", "50001")
}

func Load() Config {
	coordinator := env("PL_MODEL_COORDINATOR", "pl-coordinator")
	fast := env("PL_MODEL_RESPONDER_FAST", "pl-responder-fast")
	return Config{
		HTTPAddr:         env("HTTP_ADDR", ":8000"),
		LogLevel:         env("LOG_LEVEL", "info"),
		ProfileURL:       strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		AllowedCallers:   list("ALLOWED_CALLER_ACCOUNTS", "powerlifting-app-backend,pl-coach-discord"),
		DaprGRPCEndpoint: daprEndpoint(),
		LiteLLMBaseURL:   strings.TrimRight(env("LITELLM_BASE_URL", "http://litellm:4000"), "/"),
		LiteLLMAPIKey:    env("LITELLM_API_KEY", ""),
		MCPURL:           env("LITELLM_MCP_URL", ""),
		MCPAliases:       list("LITELLM_MCP_ALIASES", "sessions,program,competition,profile,glossary,goals,templates,weight_log,performance,analytics,calculations,lift_profiles"),
		MCPSeparator:     env("LITELLM_MCP_TOOL_SEPARATOR", "-"),
		PrivateKeyPEM:    env("PL_JOB_TOKEN_PRIVATE_KEY", ""),
		TokenTTL:         time.Duration(number("JOB_TOKEN_TTL_SECONDS", 300)) * time.Second,
		PGHost:           env("PGHOST", "assistant-postgres-rw"),
		PGPort:           env("PGPORT", "5432"),
		PGDatabase:       env("PGDATABASE", "assistant"),
		PGUser:           env("PGUSER", "assistant"),
		PGPassword:       env("PGPASSWORD", ""),
		PGSSLMode:        env("PGSSLMODE", "require"),
		EmbedDim:         number("EMBED_DIM", 1536),
		MaxConcurrency:   number("ASSISTANT_MAX_CONCURRENCY", 4),
		MaxSteps:         number("AGENT_MAX_STEPS", 12),
		MaxTokens:        number("AGENT_MAX_TOKENS", 60000),
		MaxDepth:         number("AGENT_MAX_DEPTH", 3),
		DelegationBudget: number("PL_DELEGATION_BUDGET", 6),
		ApprovalTimeout:  time.Duration(number("APPROVAL_TIMEOUT_HOURS", 24)) * time.Hour,
		RatePerMinute:    number("TURNS_PER_MINUTE", 12),
		CoordinatorModel: coordinator,
		FastModel:        fast,
		StrongModel:      env("PL_MODEL_STRONG", coordinator),
		WebModel:         env("PL_MODEL_WEB", ""),
		SecurityModel:    env("PL_MODEL_SECURITY", "pl-light"),
		EmbedModel:       env("PL_MODEL_EMBED", "pl-embed"),
		SubagentModels: map[string]string{
			"template-phase": env("PL_MODEL_SUBAGENT_TEMPLATE_PHASE", coordinator),
			"session-design": env("PL_MODEL_SUBAGENT_SESSION_DESIGN", coordinator),
			"goals":          env("PL_MODEL_SUBAGENT_GOALS", fast),
			"supplements":    env("PL_MODEL_SUBAGENT_SUPPLEMENTS", fast),
			"biometrics":     env("PL_MODEL_SUBAGENT_BIOMETRICS", fast),
			"research":       env("PL_MODEL_SUBAGENT_RESEARCH", coordinator),
		},
	}
}
