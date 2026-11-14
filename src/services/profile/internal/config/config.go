package config

import (
	"os"
	"strings"
)

type Config struct {
	HTTPAddr      string
	ValkeyURL     string
	Region        string
	LogLevel      string
	AnalyticsURL  string
	DiscordToken  string
	VideosBucket  string
	UserTable     string
	RequestsTable string
	Notifications string
	TagsTable     string
	HealthTable   string
	SessionsTable string
	Competitions  string
	VideosTable   string
	SentIndex     string
	InboxIndex    string
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
		ValkeyURL:     env("VALKEY_URL", "redis://pl-valkey:6379"),
		Region:        env("AWS_REGION", "ca-central-1"),
		LogLevel:      env("LOG_LEVEL", "info"),
		AnalyticsURL:  strings.TrimRight(strings.ReplaceAll(env("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000"), "{domain}", "analytics"), "/"),
		DiscordToken:  os.Getenv("DISCORD_BOT_TOKEN"),
		VideosBucket:  env("VIDEOS_BUCKET", "powerlifting-session-videos"),
		UserTable:     env("IF_USER_TABLE", "if-user"),
		RequestsTable: env("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"),
		Notifications: env("IF_POWERLIFTING_NOTIFICATIONS_TABLE", "if-powerlifting-notifications"),
		TagsTable:     env("POWERLIFTING_TAGS_TABLE", "if-powerlifting-tags"),
		HealthTable:   env("IF_HEALTH_TABLE_NAME", "if-health"),
		SessionsTable: env("IF_SESSIONS_TABLE_NAME", "if-sessions"),
		Competitions:  env("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"),
		VideosTable:   env("WORKOUT_VIDEOS_TABLE_NAME", "workout-Videos"),
		SentIndex:     env("IF_POWERLIFTING_REQUESTS_SENT_INDEX", "SentIndex"),
		InboxIndex:    env("IF_POWERLIFTING_REQUESTS_INBOX_INDEX", "InboxIndex"),
	}
}
