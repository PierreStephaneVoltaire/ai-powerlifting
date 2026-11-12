package config

import (
	"os"
	"strings"
)

type Config struct {
	HTTPAddr       string
	GRPCAddr       string
	ProfileURL     string
	AnalyticsGRPC  string
	Bucket         string
	AllowedCallers []string
	LogLevel       string
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func Load() Config {
	callers := strings.Split(env("EXPORT_GRPC_ALLOWED_CALLERS", "pl-analytics-ai"), ",")
	allowed := make([]string, 0, len(callers))
	for _, caller := range callers {
		if caller = strings.TrimSpace(caller); caller != "" {
			allowed = append(allowed, caller)
		}
	}
	return Config{
		HTTPAddr:       env("HTTP_ADDR", ":8000"),
		GRPCAddr:       env("GRPC_ADDR", ":50051"),
		ProfileURL:     strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"),
		AnalyticsGRPC:  env("ANALYTICS_GRPC_URL", "pl-analytics:50051"),
		Bucket:         env("POWERLIFTING_S3_BUCKET", ""),
		AllowedCallers: allowed,
		LogLevel:       env("LOG_LEVEL", "info"),
	}
}
