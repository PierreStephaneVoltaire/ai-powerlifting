package main

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/redis/go-redis/v9"

	analyticsv1 "powerlifting/analytics-ai/gen/analytics"
	exportv1 "powerlifting/analytics-ai/gen/export"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/coach"
	"powerlifting/analytics-ai/internal/config"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/data"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
	"powerlifting/analytics-ai/internal/grpcapi"
	"powerlifting/analytics-ai/internal/httpapi"
	"powerlifting/analytics-ai/internal/service"
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
	cfg := config.FromEnv()
	if cfg.CoachURL == "" {
		return errors.New("IF_API_URL is required")
	}
	registry, err := contract.Load()
	if err != nil {
		return err
	}
	options, err := redis.ParseURL(cfg.ValkeyURL)
	if err != nil {
		return err
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(), awsconfig.WithRegion(cfg.Region))
	if err != nil {
		return err
	}
	analyticsConn, err := data.Dial(cfg.AnalyticsGRPC)
	if err != nil {
		return err
	}
	defer analyticsConn.Close()
	exportConn, err := data.Dial(cfg.ExportGRPC)
	if err != nil {
		return err
	}
	defer exportConn.Close()

	kv := cache.Redis{Client: redis.NewClient(options)}
	httpClient := &http.Client{}
	svc := &service.Service{
		Registry:   registry,
		Access:     auth.ProfileClient{URL: cfg.ProfileURL, HTTP: httpClient},
		Coach:      coach.HTTP{URL: cfg.CoachURL, Client: httpClient},
		Source:     data.Analytics{Client: analyticsv1.NewAnalyticsDataClient(analyticsConn)},
		Exporter:   data.Export{Client: exportv1.NewExportsClient(exportConn)},
		KV:         kv,
		Backend:    generation.Dynamo{API: dynamodb.NewFromConfig(awsCfg), Table: cfg.Table},
		Executions: execution.New(cache.Prompts{KV: kv}),
		Now:        time.Now,
	}

	httpServer := &http.Server{Addr: ":" + cfg.Port, Handler: httpapi.New(&httpapi.API{Service: svc, Domain: contract.Domain}), ReadHeaderTimeout: 10 * time.Second}
	grpcServer := grpcapi.New(&grpcapi.Server{Service: svc, Now: time.Now}, cfg.AllowedCallers)
	listener, err := net.Listen("tcp", ":"+cfg.GRPCPort)
	if err != nil {
		return err
	}

	stop, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	failures := make(chan error, 2)
	go func() { failures <- httpServer.ListenAndServe() }()
	go func() { failures <- grpcServer.Serve(listener) }()
	slog.Info("serving", "http", cfg.Port, "grpc", cfg.GRPCPort)

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
	done := make(chan struct{})
	go func() { grpcServer.GracefulStop(); close(done) }()
	_ = httpServer.Shutdown(ctx)
	select {
	case <-done:
	case <-ctx.Done():
		grpcServer.Stop()
	}
	return nil
}
