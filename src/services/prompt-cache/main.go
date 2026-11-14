package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"powerlifting/prompt-cache/internal/config"
	"powerlifting/prompt-cache/internal/decision"
	"powerlifting/prompt-cache/internal/httpapi"
	"powerlifting/prompt-cache/internal/lookup"
	"powerlifting/prompt-cache/internal/semantic"
	"powerlifting/prompt-cache/internal/store"
)

const shutdownGrace = 20 * time.Second

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := run(); err != nil {
		slog.Error("service stopped", "error", err)
		os.Exit(1)
	}
}

func decider(cfg config.Config) decision.Decider {
	if cfg.OpenAIKey == "" {
		slog.Warn("OPENAI_API_KEY is not set; semantic decisions always miss")
		return decision.Miss{}
	}
	return decision.OpenAI{URL: cfg.DecisionsURL, Key: cfg.OpenAIKey, Model: cfg.DecisionModel, MinConfidence: cfg.MinConfidence, HTTP: &http.Client{}}
}

func run() error {
	cfg := config.FromEnv()
	options, err := redis.ParseURL(cfg.ValkeyURL)
	if err != nil {
		return err
	}
	service := lookup.Service{
		Entries:         store.Valkey{Client: redis.NewClient(options), TTL: cfg.EntryTTL},
		Index:           semantic.MCP{URL: cfg.MCPURL},
		Decider:         decider(cfg),
		CandidateLimit:  cfg.CandidateLimit,
		SemanticTimeout: cfg.SemanticTimeout,
		DecisionTimeout: cfg.DecisionTimeout,
		StoreTimeout:    cfg.StoreTimeout,
	}
	server := &http.Server{Addr: ":" + cfg.Port, Handler: httpapi.API{Service: service}.Handler(), ReadHeaderTimeout: 10 * time.Second}

	stop, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	failures := make(chan error, 1)
	go func() { failures <- server.ListenAndServe() }()
	slog.Info("serving", "http", cfg.Port)

	select {
	case err := <-failures:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-stop.Done():
	}
	slog.Info("shutting down")
	ctx, release := context.WithTimeout(context.Background(), shutdownGrace)
	defer release()
	return server.Shutdown(ctx)
}
