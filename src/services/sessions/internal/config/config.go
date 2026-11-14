package config

import (
	"os"
	"strings"
)

type Config struct {
	HTTPAddr      string
	ProfileURL    string
	ValkeyURL     string
	Region        string
	SessionsTable string
	HealthTable   string
	LogLevel      string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func Load() Config {
	return Config{
		HTTPAddr:      env("HTTP_ADDR", ":8000"),
		ProfileURL:    strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		ValkeyURL:     env("VALKEY_URL", "redis://pl-valkey:6379"),
		Region:        env("AWS_REGION", "ca-central-1"),
		SessionsTable: env("IF_SESSIONS_TABLE_NAME", "if-sessions"),
		HealthTable:   env("IF_HEALTH_TABLE_NAME", "if-health"),
		LogLevel:      env("LOG_LEVEL", "info"),
	}
}
