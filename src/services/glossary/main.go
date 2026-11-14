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

	"powerlifting/glossary/internal/athlete"
	"powerlifting/glossary/internal/auth"
	"powerlifting/glossary/internal/cache"
	"powerlifting/glossary/internal/coach"
	"powerlifting/glossary/internal/config"
	"powerlifting/glossary/internal/contract"
	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/generic"
	"powerlifting/glossary/internal/serve"
	"powerlifting/glossary/internal/service"
	"powerlifting/glossary/internal/store"
)

const shutdownGrace = 20 * time.Second

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := run(); err != nil {
		slog.Error("service stopped", "error", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.FromEnv()
	if err != nil {
		return err
	}
	registry, err := contract.Load()
	if err != nil {
		return err
	}
	options, err := redis.ParseURL(cfg.ValkeyURL)
	if err != nil {
		return err
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background())
	if err != nil {
		return err
	}
	api := dynamodb.NewFromConfig(awsCfg)
	valkey := cache.Valkey{Client: redis.NewClient(options)}
	httpClient := &http.Client{}
	glossary := store.Dynamo{API: api, Table: cfg.GlossaryTable}
	jobs := coach.HTTP{URL: cfg.CoachURL, Client: httpClient}
	estimator := &generic.Estimator{Store: glossary, Coach: jobs, Interval: cfg.GenericInterval, Now: time.Now}
	svc, err := service.New(&service.Service{
		Registry:   registry,
		Access:     auth.ProfileClient{URL: cfg.ProfileURL, HTTP: httpClient},
		Store:      glossary,
		Athletes:   athlete.Dynamo{API: api, HealthTable: cfg.HealthTable, SessionsTable: cfg.SessionsTable},
		Coach:      jobs,
		Executions: execution.New(cache.Prompts{Valkey: valkey, URL: cfg.PromptCacheURL, HTTP: httpClient, Now: time.Now}),
		Generic:    estimator,
		Cache:      valkey,
		Now:        time.Now,
	})
	if err != nil {
		return err
	}

	stop, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	go estimator.Run(stop)

	server := &http.Server{Addr: ":" + cfg.Port, Handler: serve.New(&serve.API{Service: svc, Domain: contract.Domain}), ReadHeaderTimeout: 10 * time.Second}
	failures := make(chan error, 1)
	go func() { failures <- server.ListenAndServe() }()
	slog.Info("serving", "port", cfg.Port)

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
