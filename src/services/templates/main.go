package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/redis/go-redis/v9"
	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/cache"
	"powerlifting/templates/internal/coach"
	"powerlifting/templates/internal/contract"
	"powerlifting/templates/internal/domain"
	"powerlifting/templates/internal/execution"
	"powerlifting/templates/internal/library"
	"powerlifting/templates/internal/serve"
	"powerlifting/templates/internal/service"
	"powerlifting/templates/internal/store"
)

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	registry, err := contract.Load()
	if err != nil {
		log.Error("load operations", "error", err)
		os.Exit(1)
	}
	cfg, err := awsconfig.LoadDefaultConfig(context.Background(), awsconfig.WithRegion(env("AWS_REGION", "ca-central-1")))
	if err != nil {
		log.Error("AWS configuration", "error", err)
		os.Exit(1)
	}
	options, err := redis.ParseURL(env("VALKEY_URL", "redis://pl-valkey:6379"))
	if err != nil {
		log.Error("invalid cache URL", "error", err)
		os.Exit(1)
	}
	options.ReadTimeout, options.WriteTimeout, options.DialTimeout = 2*time.Second, 2*time.Second, 2*time.Second
	cacheClient := redis.NewClient(options)
	defer cacheClient.Close()
	glossaryTable := os.Getenv("GLOSSARY_TABLE_NAME")
	if glossaryTable == "" {
		log.Error("missing glossary table")
		os.Exit(1)
	}
	backend := store.Repository{Client: dynamodb.NewFromConfig(cfg), Table: env("IF_TEMPLATES_TABLE_NAME", "if-health-templates"), HealthTable: env("IF_HEALTH_TABLE_NAME", "if-health"), GlossaryTable: glossaryTable, SessionsTable: env("IF_SESSIONS_TABLE_NAME", "if-sessions")}
	svc := &service.Service{Domain: domain.Client{URLTemplate: env("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000")}, Sources: backend, Registry: registry, Access: auth.NewAccess(strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/")), Library: library.Library{Backend: backend, Partition: env("IF_TEMPLATES_LIBRARY_PK", "template_library")}, Claims: backend, Coach: coach.HTTP{URL: env("IF_API_URL", "http://pl-coach:8000"), Client: &http.Client{Timeout: 40 * time.Second}}, Executions: execution.New(cache.Prompts{Versions: cache.Versions{Client: cacheClient}, URL: env("PROMPT_CACHE_URL", "http://pl-prompt-cache-api:8000")})}
	server := &http.Server{Addr: ":" + env("PORT", "8000"), Handler: serve.Handler(svc, log), ReadHeaderTimeout: 10 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	failures := make(chan error, 1)
	go func() { failures <- server.ListenAndServe() }()
	select {
	case err = <-failures:
		if !errors.Is(err, http.ErrServerClosed) {
			log.Error("server stopped", "error", err)
			os.Exit(1)
		}
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdown); err != nil {
			log.Error("shutdown failed", "error", err)
		}
	}
}
