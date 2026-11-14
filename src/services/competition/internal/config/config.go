package config

import (
	"os"
	"strings"
)

type Config struct {
	HTTPAddr      string
	Region        string
	ProfileURL    string
	ValkeyURL     string
	EntriesTable  string
	HealthTable   string
	SessionsTable string
	LogLevel      string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func Load() Config {
	addr := env("HTTP_ADDR", "")
	if addr == "" {
		addr = ":" + env("PORT", "8000")
	}
	return Config{
		HTTPAddr:      addr,
		Region:        env("AWS_REGION", "ca-central-1"),
		ProfileURL:    strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		ValkeyURL:     env("VALKEY_URL", "redis://pl-valkey:6379"),
		EntriesTable:  env("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"),
		HealthTable:   env("IF_HEALTH_TABLE_NAME", "if-health"),
		SessionsTable: env("IF_SESSIONS_TABLE_NAME", "if-sessions"),
		LogLevel:      env("LOG_LEVEL", "info"),
	}
}
