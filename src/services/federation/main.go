package main

import (
	"context"
	"errors"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/redis/go-redis/v9"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"powerlifting/federation/internal/auth"
	"powerlifting/federation/internal/contract"
	"powerlifting/federation/internal/serve"
	"powerlifting/federation/internal/service"
	"powerlifting/federation/internal/store"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	registry, err := contract.Load()
	if err != nil {
		log.Error("load operations", "error", err)
		os.Exit(1)
	}
	profile := os.Getenv("PL_PROFILE_URL")
	if profile == "" {
		profile = "http://pl-profile:8000"
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "ca-central-1"
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(), awsconfig.WithRegion(region))
	if err != nil {
		log.Error("load AWS config", "error", err)
		os.Exit(1)
	}
	table := os.Getenv("IF_HEALTH_TABLE_NAME")
	if table == "" {
		table = "if-health"
	}
	valkeyURL := os.Getenv("VALKEY_URL")
	if valkeyURL == "" {
		valkeyURL = "redis://pl-valkey:6379"
	}
	options, err := redis.ParseURL(valkeyURL)
	if err != nil {
		log.Error("invalid Valkey URL", "error", err)
		os.Exit(1)
	}
	options.ReadTimeout, options.WriteTimeout, options.DialTimeout = 2*time.Second, 2*time.Second, 2*time.Second
	client := redis.NewClient(options)
	defer client.Close()
	masterTable := os.Getenv("POWERLIFTING_MASTER_FEDERATIONS_TABLE")
	if masterTable == "" {
		masterTable = "if-powerlifting-master-federations"
	}
	svc := service.New(registry, auth.NewAccess(strings.TrimRight(profile, "/")), store.Store{DB: dynamodb.NewFromConfig(awsCfg), Table: table, MasterTable: masterTable}, store.Valkey{Client: client}, log)
	server := &http.Server{Addr: ":" + port, Handler: serve.Handler(svc, log), ReadHeaderTimeout: 10 * time.Second}
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
