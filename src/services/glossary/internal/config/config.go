package config

import (
	"fmt"
	"os"
	"strings"
	"time"
)

type Config struct {
	Port            string
	ProfileURL      string
	ValkeyURL       string
	PromptCacheURL  string
	CoachURL        string
	GlossaryTable   string
	HealthTable     string
	SessionsTable   string
	GenericInterval time.Duration
}

func FromEnv() (Config, error) {
	var missing []string
	required := func(name string) string {
		value := os.Getenv(name)
		if value == "" {
			missing = append(missing, name)
		}
		return value
	}
	cfg := Config{
		Port:           "8000",
		ProfileURL:     strings.TrimRight(required("PL_PROFILE_URL"), "/"),
		ValkeyURL:      required("VALKEY_URL"),
		PromptCacheURL: strings.TrimRight(required("PROMPT_CACHE_URL"), "/"),
		CoachURL:       strings.TrimRight(required("IF_API_URL"), "/"),
		GlossaryTable:  required("GLOSSARY_TABLE_NAME"),
		HealthTable:    required("IF_HEALTH_TABLE_NAME"),
		SessionsTable:  required("IF_SESSIONS_TABLE_NAME"),
	}
	if port := os.Getenv("PORT"); port != "" {
		cfg.Port = port
	}
	interval := required("GLOSSARY_GENERIC_INTERVAL")
	if len(missing) > 0 {
		return Config{}, fmt.Errorf("missing environment: %s", strings.Join(missing, ", "))
	}
	parsed, err := time.ParseDuration(interval)
	if err != nil || parsed <= 0 {
		return Config{}, fmt.Errorf("GLOSSARY_GENERIC_INTERVAL must be a positive duration: %q", interval)
	}
	cfg.GenericInterval = parsed
	return cfg, nil
}
