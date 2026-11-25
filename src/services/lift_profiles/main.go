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

	"powerlifting/liftprofiles/internal/auth"
	"powerlifting/liftprofiles/internal/cache"
	"powerlifting/liftprofiles/internal/coach"
	"powerlifting/liftprofiles/internal/contract"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
	"powerlifting/liftprofiles/internal/serve"
	"powerlifting/liftprofiles/internal/service"
)

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func run() error {
	registry, err := contract.Load()
	if err != nil {
		return err
	}
	defs, err := profile.Defaults()
	if err != nil {
		return err
	}
	options, err := redis.ParseURL(env("VALKEY_URL", "redis://pl-valkey:6379"))
	if err != nil {
		return err
	}
	options.ReadTimeout, options.WriteTimeout, options.DialTimeout = 2*time.Second, 2*time.Second, 2*time.Second
	client := redis.NewClient(options)
	defer client.Close()
	awsConfig, err := awsconfig.LoadDefaultConfig(context.Background(), awsconfig.WithRegion(env("AWS_REGION", "ca-central-1")))
	if err != nil {
		return err
	}
	httpClient := &http.Client{}
	versions := cache.Store{Client: client}
	programs := service.Programs{DB: dynamodb.NewFromConfig(awsConfig), Table: env("IF_HEALTH_TABLE_NAME", "if-health"), Definitions: defs, Bump: versions.BumpAnalysis}
	svc := &service.Service{
		Registry:   registry,
		Access:     auth.ProfileClient{URL: strings.TrimRight(env("PL_PROFILE_URL", "http://pl-profile:8000"), "/"), HTTP: httpClient},
		Coach:      coach.HTTP{URL: env("IF_API_URL", "http://pl-coach:8000"), Client: httpClient},
		Executions: execution.New(cache.Prompts{Versions: versions, URL: env("PROMPT_CACHE_URL", "http://pl-prompt-cache-api:8000"), HTTP: httpClient}),
		Handlers: map[string]func(context.Context, map[string]any, execution.Inferer) (any, error){
			"program_update_lift_profiles":   programs.Update,
			"lift_profile_suggest":           service.Suggest(defs),
			"lift_profile_estimate_stimulus": service.Stimulus(defs, programs),
			"fatigue_profile_estimate":       service.ExerciseEstimate(defs, programs, false),
			"muscle_group_estimate":          service.ExerciseEstimate(defs, programs, true),
		},
	}
	server := &http.Server{Addr: ":" + env("PORT", "8000"), Handler: serve.New(&serve.API{Service: svc, Domain: contract.Domain}), ReadHeaderTimeout: 10 * time.Second}
	stop, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	errorsCh := make(chan error, 1)
	go func() { errorsCh <- server.ListenAndServe() }()
	select {
	case err = <-errorsCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-stop.Done():
	}
	shutdown, release := context.WithTimeout(context.Background(), 20*time.Second)
	defer release()
	return server.Shutdown(shutdown)
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := run(); err != nil {
		slog.Error("service stopped", "error", err)
		os.Exit(1)
	}
}
