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

	"powerlifting/calculations/internal/auth"
	"powerlifting/calculations/internal/contract"
	"powerlifting/calculations/internal/serve"
	"powerlifting/calculations/internal/service"
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
	server := &http.Server{Addr: ":" + port, Handler: serve.Handler(service.New(registry, auth.NewAccess(strings.TrimRight(profile, "/"))), log), ReadHeaderTimeout: 10 * time.Second}
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
