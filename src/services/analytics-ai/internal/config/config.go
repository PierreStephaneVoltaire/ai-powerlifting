package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port           string
	GRPCPort       string
	ProfileURL     string
	ValkeyURL      string
	CoachURL       string
	AnalyticsGRPC  string
	ExportGRPC     string
	AllowedCallers []string
	Table          string
	Region         string
}

func value(name, fallback string) string {
	if text := os.Getenv(name); text != "" {
		return text
	}
	return fallback
}

func FromEnv() Config {
	callers := []string{}
	for _, caller := range strings.Split(value("AI_GRPC_ALLOWED_CALLERS", "pl-analytics"), ",") {
		if caller = strings.TrimSpace(caller); caller != "" {
			callers = append(callers, caller)
		}
	}
	return Config{
		Port:           port(value("PORT", "8000")),
		GRPCPort:       port(value("GRPC_PORT", "50051")),
		ProfileURL:     strings.TrimRight(value("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		ValkeyURL:      value("VALKEY_URL", "redis://pl-valkey:6379"),
		CoachURL:       strings.TrimRight(os.Getenv("IF_API_URL"), "/"),
		AnalyticsGRPC:  value("ANALYTICS_GRPC_URL", "pl-analytics:50051"),
		ExportGRPC:     value("EXPORT_GRPC_URL", "pl-analytics-export:50051"),
		AllowedCallers: callers,
		Table:          value("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"),
		Region:         value("AWS_REGION", "ca-central-1"),
	}
}

func port(text string) string {
	if _, err := strconv.Atoi(text); err != nil {
		return "8000"
	}
	return text
}
