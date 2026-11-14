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
	"github.com/aws/aws-sdk-go-v2/service/s3"

	"powerlifting/analytics-export/internal/auth"
	"powerlifting/analytics-export/internal/config"
	"powerlifting/analytics-export/internal/contract"
	"powerlifting/analytics-export/internal/data"
	"powerlifting/analytics-export/internal/grpcsrv"
	"powerlifting/analytics-export/internal/serve"
	"powerlifting/analytics-export/internal/service"
	"powerlifting/analytics-export/internal/store"
)

const shutdownGrace = 20 * time.Second

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
	if cfg.Bucket == "" {
		return errors.New("POWERLIFTING_S3_BUCKET is required")
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx)
	if err != nil {
		return err
	}
	objects := store.NewS3(s3.NewFromConfig(awsCfg), cfg.Bucket)
	bundles, err := data.Dial(cfg.AnalyticsGRPC)
	if err != nil {
		return err
	}
	defer bundles.Close()
	svc, err := service.New(registry, auth.NewAccess(cfg.ProfileURL), bundles, objects, time.Now)
	if err != nil {
		return err
	}

	httpServer := &http.Server{Addr: cfg.HTTPAddr, Handler: serve.Handler(svc, log), ReadHeaderTimeout: 10 * time.Second}
	grpcServer := grpcsrv.New(cfg.AllowedCallers, &grpcsrv.Exports{Store: objects, Now: time.Now})

	failures := make(chan error, 2)
	go func() { failures <- httpServer.ListenAndServe() }()
	go func() { failures <- grpcsrv.Serve(grpcServer, cfg.GRPCAddr) }()
	log.Info("started", "http", cfg.HTTPAddr, "grpc", cfg.GRPCAddr)

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
	stopped := make(chan struct{})
	go func() {
		grpcServer.GracefulStop()
		close(stopped)
	}()
	select {
	case <-stopped:
	case <-shutdown.Done():
		grpcServer.Stop()
	}
	return httpServer.Shutdown(shutdown)
}
