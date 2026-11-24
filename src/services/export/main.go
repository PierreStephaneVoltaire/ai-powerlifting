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

	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
	"powerlifting/export/internal/data"
	"powerlifting/export/internal/hydration"
	"powerlifting/export/internal/serve"
	"powerlifting/export/internal/service"
	"powerlifting/export/internal/store"
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
	cacheURL := os.Getenv("VALKEY_URL")
	if cacheURL == "" {
		cacheURL = "redis://pl-valkey:6379"
	}
	options, err := redis.ParseURL(cacheURL)
	if err != nil {
		log.Error("invalid cache URL", "error", err)
		os.Exit(1)
	}
	options.ReadTimeout, options.WriteTimeout, options.DialTimeout = 2*time.Second, 2*time.Second, 2*time.Second
	client := redis.NewClient(options)
	defer client.Close()
	competitionTable := os.Getenv("POWERLIFTING_USER_COMPETITIONS_TABLE")
	if competitionTable == "" {
		competitionTable = "if-powerlifting-user-competitions"
	}
	db := dynamodb.NewFromConfig(awsCfg)
	svc := service.New(registry, auth.NewAccess(strings.TrimRight(profile, "/")), store.Store{DB: db, Table: table, CompetitionTable: competitionTable}, store.Cache{Client: client}, log)
	svc.Cache = store.Cache{Client: client}
	sessionsTable := os.Getenv("IF_SESSIONS_TABLE_NAME")
	if sessionsTable == "" {
		sessionsTable = "if-sessions"
	}
	supplementsTable := os.Getenv("IF_SUPPLEMENTS_TABLE_NAME")
	if supplementsTable == "" {
		supplementsTable = "if-supplements"
	}
	svc.Programs = hydration.Loader{Reader: store.Reader{DB: db, CompetitionTable: competitionTable}, Tables: hydration.Tables{Health: table, Sessions: sessionsTable, Supplements: supplementsTable}}
	analyticsURL := os.Getenv("PL_ANALYTICS_URL")
	if analyticsURL == "" {
		analyticsURL = "http://pl-analytics:8000"
	}
	svc.Analytics = data.AnalyticsClient{URL: analyticsURL}
	serviceURL := os.Getenv("PL_SERVICE_URL_TEMPLATE")
	if serviceURL == "" {
		serviceURL = "http://pl-{domain}:8000"
	}
	svc.Domain = data.DomainClient{URLTemplate: serviceURL}
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
