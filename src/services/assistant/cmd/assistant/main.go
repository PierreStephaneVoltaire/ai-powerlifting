package main

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	dw "github.com/dapr/durabletask-go/workflow"

	"powerlifting/assistant/internal/access"
	"powerlifting/assistant/internal/activities"
	"powerlifting/assistant/internal/audit"
	"powerlifting/assistant/internal/config"
	"powerlifting/assistant/internal/domainjobs"
	"powerlifting/assistant/internal/httpapi"
	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/reference"
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

func referenceClient(cfg config.Config) *llm.Client {
	if cfg.ReferenceLiteLLMURL == "" || cfg.ReferenceLiteLLMKey == "" || cfg.ReferenceLiteLLMURL == cfg.LiteLLMBaseURL {
		return nil
	}
	return llm.New(cfg.ReferenceLiteLLMURL, cfg.ReferenceLiteLLMKey)
}

func loadDomainJobs(ctx context.Context, cfg config.Config, d *activities.Deps) (*domainjobs.Service, error) {
	modelConfig := os.Getenv("PL_DOMAIN_OPERATION_AI")
	catalog, models, err := domainjobs.LoadCatalog("/operations", "/permissions.json", modelConfig)
	if err != nil {
		return nil, err
	}
	jobs := &domainjobs.Service{
		Store: d.Store, Access: d.Access, Catalog: catalog, Models: models, Chat: d.Chat,
		HTTP: &http.Client{Timeout: time.Minute}, ServiceURL: os.Getenv("PL_SERVICE_URL_TEMPLATE"),
	}
	if jobs.ServiceURL == "" {
		jobs.ServiceURL = "http://pl-{domain}:8000"
	}
	if bucket := os.Getenv("PL_DOMAIN_LIFETIME_BUCKET"); bucket != "" {
		awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.AWSRegion))
		if err != nil {
			return nil, err
		}
		client := s3.NewFromConfig(awsCfg)
		jobs.Lifetime = func(ctx context.Context, athlete string) (string, error) {
			key := "lifetime/" + athlete + "/latest.md"
			object, err := client.GetObject(ctx, &s3.GetObjectInput{Bucket: &bucket, Key: &key})
			if err != nil {
				return "", err
			}
			defer object.Body.Close()
			body, err := io.ReadAll(object.Body)
			return string(body), err
		}
	}
	return jobs, nil
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
	llmClient := llm.New(cfg.LiteLLMBaseURL, cfg.LiteLLMAPIKey)
	var references interface {
		Search(context.Context, reference.SearchRequest) ([]reference.Passage, error)
	}
	referenceLLM := referenceClient(cfg)
	if cfg.ReferenceBucket != "" && referenceLLM == nil {
		log.Warn("reference indexing disabled: private model endpoint is not configured")
	}
	if cfg.ReferenceBucket != "" && referenceLLM != nil {
		awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.AWSRegion))
		if err != nil {
			return errors.New("reference AWS configuration unavailable")
		}
		referenceStore, err := reference.New(reference.Config{
			Pool: db.Pool, S3: s3.NewFromConfig(awsCfg), Bucket: cfg.ReferenceBucket,
			Collections: []reference.Collection{
				{Name: "supplements", Prefix: "references/supplements/", Scope: "supplements"},
				{Name: "federations", Prefix: "references/federation-rules/", Scope: "federation:*"},
			},
			Embed: func(ctx context.Context, text string) ([]float32, error) {
				return referenceLLM.EmbedPrivate(ctx, cfg.EmbedModel, text)
			},
			EmbedBatch: func(ctx context.Context, texts []string) ([][]float32, error) {
				return referenceLLM.EmbedPrivateBatch(ctx, cfg.EmbedModel, texts)
			},
			EmbedDim: cfg.EmbedDim, BatchSize: 32,
		})
		if err != nil {
			return errors.New("reference importer initialization failed")
		}
		references = referenceStore
		go func() {
			if err := referenceStore.Start(ctx); err != nil && ctx.Err() == nil {
				log.Warn("reference scan stopped", "error", "reference scan error")
			}
		}()
	}
	deps := &activities.Deps{
		Config: cfg, Store: db, Access: resolver, Audit: recorder,
		LLM: llmClient, ReferenceLLM: referenceLLM, Reference: references,
		MCP:    tools.NewMCPClient(cfg.MCPURL, cfg.LiteLLMAPIKey, cfg.MCPAliases, cfg.MCPSeparator),
		Signer: signer, Log: log, Slots: make(chan struct{}, cfg.MaxConcurrency), Now: time.Now,
	}
	deps.DomainJobs, err = loadDomainJobs(ctx, cfg, deps)
	if err != nil {
		return err
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

	api := &httpapi.Server{Store: db, Access: resolver, Audit: recorder, Engine: engine, DomainJobs: deps.DomainJobs, Log: log, AllowedCallers: cfg.AllowedCallers, Now: time.Now}
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
