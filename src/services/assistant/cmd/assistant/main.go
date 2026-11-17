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

	dw "github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/audit"
	"powerlifting/assistant/internal/config"
	"powerlifting/assistant/internal/httpapi"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/store"
	"powerlifting/assistant/internal/token"
	"powerlifting/assistant/internal/tools"
	"powerlifting/assistant/internal/workflow"
)

const (
	shutdownGrace = 20 * time.Second
	workerRetries = 30
	workerBackoff = 2 * time.Second
)

func main() {
	cfg := config.Load()
	var level slog.Level
	_ = level.UnmarshalText([]byte(cfg.LogLevel))
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level}))
	if err := run(cfg, log); err != nil {
		log.Error("fatal", "error", err)
		os.Exit(1)
	}
}

func startWorker(ctx context.Context, engine *workflow.Engine, registry *dw.Registry, log *slog.Logger) error {
	var err error
	for attempt := 0; attempt < workerRetries; attempt++ {
		if err = engine.StartWorker(ctx, registry); err == nil {
			return nil
		}
		log.Warn("dapr sidecar not ready", "attempt", attempt+1, "error", err)
		select {
		case <-time.After(workerBackoff):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return err
}

func run(cfg config.Config, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	signer, err := token.NewSigner(cfg.PrivateKeyPEM, cfg.TokenTTL)
	if err != nil {
		return err
	}
	if cfg.MCPURL == "" {
		cfg.MCPURL = cfg.LiteLLMBaseURL + "/mcp/"
	}
	db, err := store.Open(ctx, store.ConnConfig{Host: cfg.PGHost, Port: cfg.PGPort, Database: cfg.PGDatabase, User: cfg.PGUser, Password: cfg.PGPassword, SSLMode: cfg.PGSSLMode}, cfg.EmbedDim)
	if err != nil {
		return err
	}
	defer db.Close()

	recorder := &audit.Recorder{Store: db, Log: log}
	resolver := access.New(cfg.ProfileURL)
	deps := &activities.Deps{
		Config: cfg, Store: db, Access: resolver, Audit: recorder,
		LLM:    llm.New(cfg.LiteLLMBaseURL, cfg.LiteLLMAPIKey),
		MCP:    tools.NewMCPClient(cfg.MCPURL, cfg.LiteLLMAPIKey, cfg.MCPAliases, cfg.MCPSeparator),
		Signer: signer, Log: log, Slots: make(chan struct{}, cfg.MaxConcurrency), Now: time.Now,
	}

	registry := dw.NewRegistry()
	if err := activities.Register(registry, deps); err != nil {
		return err
	}
	if err := (&workflow.Workflows{Config: cfg}).Register(registry); err != nil {
		return err
	}
	engine, err := workflow.Connect(cfg.DaprGRPCEndpoint, os.Getenv("DAPR_API_TOKEN"))
	if err != nil {
		return err
	}
	defer engine.Close()
	if err := startWorker(ctx, engine, registry, log); err != nil {
		return err
	}

	api := &httpapi.Server{Store: db, Access: resolver, Audit: recorder, Engine: engine, Log: log, AllowedCallers: cfg.AllowedCallers, Now: time.Now}
	server := &http.Server{Addr: cfg.HTTPAddr, Handler: api.Handler(), ReadHeaderTimeout: 10 * time.Second}
	failures := make(chan error, 1)
	go func() { failures <- server.ListenAndServe() }()
	log.Info("started", "http", cfg.HTTPAddr, "dapr", cfg.DaprGRPCEndpoint)

	select {
	case err := <-failures:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
	}
	log.Info("shutting down")
	shutdown, cancel := context.WithTimeout(context.Background(), shutdownGrace)
	defer cancel()
	return server.Shutdown(shutdown)
}
