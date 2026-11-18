package config

import (
	"os"
	"strings"
)

type Config struct {
	HTTPAddr           string
	ProfileURL         string
	AnalyticsURL       string
	ValkeyURL          string
	Region             string
	HealthTable        string
	SessionsTable      string
	SupplementsTable   string
	CompetitionsTable  string
	TemplatesTable     string
	TemplatesLibraryPK string
	LogLevel           string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func Load() Config {
	return Config{
		HTTPAddr:           env("HTTP_ADDR", ":8000"),
		ProfileURL:         strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		AnalyticsURL:       strings.TrimRight(serviceURL("analytics"), "/"),
		ValkeyURL:          env("VALKEY_URL", "redis://pl-valkey:6379"),
		Region:             env("AWS_REGION", "ca-central-1"),
		HealthTable:        env("IF_HEALTH_TABLE_NAME", "if-health"),
		SessionsTable:      env("IF_SESSIONS_TABLE_NAME", "if-sessions"),
		SupplementsTable:   env("IF_SUPPLEMENTS_TABLE_NAME", "if-supplements"),
		CompetitionsTable:  env("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"),
		TemplatesTable:     env("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
		TemplatesLibraryPK: env("IF_TEMPLATES_LIBRARY_PK", "template_library"),
		LogLevel:           env("LOG_LEVEL", "info"),
	}
}

func serviceURL(domain string) string {
	template := env("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000")
	return strings.ReplaceAll(template, "{domain}", domain)
}
