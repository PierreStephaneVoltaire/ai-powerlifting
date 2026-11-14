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

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/redis/go-redis/v9"

	"powerlifting/sessions/internal/auth"
	"powerlifting/sessions/internal/config"
	"powerlifting/sessions/internal/contract"
	"powerlifting/sessions/internal/serve"
	"powerlifting/sessions/internal/service"
	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/store"
)

const (
	shutdownGrace = 20 * time.Second
	valkeyTimeout = 2 * time.Second
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

func run(cfg config.Config, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	registry, err := contract.Load()
	if err != nil {
		return err
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.Region))
	if err != nil {
		return err
	}
	options, err := redis.ParseURL(cfg.ValkeyURL)
	if err != nil {
		return err
	}
	options.DialTimeout, options.ReadTimeout, options.WriteTimeout = valkeyTimeout, valkeyTimeout, valkeyTimeout
	cache := redis.NewClient(options)
	defer cache.Close()

	tables := &store.Dynamo{API: dynamodb.NewFromConfig(awsCfg), SessionsTable: cfg.SessionsTable, HealthTable: cfg.HealthTable, Sleep: time.Sleep}
	sessions := &session.Service{Sessions: tables, Programs: tables, SourceTable: cfg.HealthTable, Now: time.Now, NewID: session.RandomID}
	svc, err := service.New(registry, auth.NewAccess(cfg.ProfileURL), sessions, store.Valkey{Client: cache, Log: log})
	if err != nil {
		return err
	}

	server := &http.Server{Addr: cfg.HTTPAddr, Handler: serve.Handler(svc, log), ReadHeaderTimeout: 10 * time.Second}
	failures := make(chan error, 1)
	go func() { failures <- server.ListenAndServe() }()
	log.Info("started", "http", cfg.HTTPAddr)

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
