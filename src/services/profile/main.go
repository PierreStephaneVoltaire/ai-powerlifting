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
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/redis/go-redis/v9"

	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/config"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/external"
	"powerlifting/profile/internal/serve"
	"powerlifting/profile/internal/service"
	"powerlifting/profile/internal/store"
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

	db := &store.DB{API: dynamodb.NewFromConfig(awsCfg), Tables: store.Tables{
		User: cfg.UserTable, Requests: cfg.RequestsTable, Notifications: cfg.Notifications, Tags: cfg.TagsTable,
		Health: cfg.HealthTable, Sessions: cfg.SessionsTable, Competitions: cfg.Competitions, Videos: cfg.VideosTable,
		SentIndex: cfg.SentIndex, InboxIndex: cfg.InboxIndex,
	}}
	svc, err := service.New(service.Deps{
		Registry:  registry,
		DB:        db,
		Env:       clock.System(),
		Versions:  store.Valkey{Client: cache, Log: log},
		Discord:   external.NewDiscord(cfg.DiscordToken, log),
		Analytics: external.NewAnalytics(cfg.AnalyticsURL, log),
		Avatars:   &external.Avatars{Client: s3.NewFromConfig(awsCfg), Bucket: cfg.VideosBucket},
	})
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
