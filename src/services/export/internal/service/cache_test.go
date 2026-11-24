package service

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"testing"
	"time"

	"powerlifting/export/internal/apperr"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
	"powerlifting/export/internal/hydration"
)

type testCache struct {
	key     string
	record  map[string]any
	written map[string]any
}

func (c *testCache) Version(context.Context, string) (string, error) { return "7", nil }
func (c *testCache) Get(_ context.Context, key string) (map[string]any, error) {
	c.key = key
	return c.record, nil
}
func (c *testCache) Set(_ context.Context, _ string, record map[string]any) error {
	c.written = record
	return nil
}

type accessValue map[string]any

func (a accessValue) Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error) {
	return a, nil
}

func TestMarkdownCacheRechecksCurrentPermissions(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	current := accessValue{"permissions": []any{"analytics:read", "competition:read"}, "competition_scope": map[string]any{"read": []any{"COMP#one"}}}
	cached := &testCache{record: map[string]any{"markdown": "private", "generated_at": "2026-11-23T12:00:00Z", "access_requirements": map[string]any{"permissions": []any{"competition:read"}, "competition_ids": []any{"COMP#two"}}}}
	svc := New(registry, current, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	svc.Now = func() time.Time { return time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC) }
	svc.Cache = cached
	caller := auth.Caller{Person: "person", Athlete: "athlete"}
	_, err = svc.Call(context.Background(), "get_analysis_markdown", map[string]any{}, caller)
	var status *apperr.Error
	if !errors.As(err, &status) || status.Status != http.StatusForbidden {
		t.Fatalf("expected forbidden, got %v", err)
	}
	cached.record["access_requirements"] = map[string]any{"permissions": []any{"competition:read"}, "competition_ids": []any{"one"}}
	result, err := svc.Call(context.Background(), "get_analysis_markdown", map[string]any{}, caller)
	if err != nil || result.(map[string]any)["cached"] != true || result.(map[string]any)["markdown"] != "private" {
		t.Fatalf("result=%#v err=%v", result, err)
	}
	if cached.key == "" {
		t.Fatal("cache was not read")
	}
}

func TestMarkdownCacheOnlyMiss(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc := New(registry, accessValue{"is_self": true}, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	svc.Cache = &testCache{}
	result, err := svc.Call(context.Background(), "get_analysis_markdown", map[string]any{"cache_only": true}, auth.Caller{Person: "person", Athlete: "athlete"})
	if err != nil || result.(map[string]any)["cache_miss"] != true {
		t.Fatalf("result=%#v err=%v", result, err)
	}
}

type testLoader struct{ program map[string]any }

func (l testLoader) Load(context.Context, string, string, string, string, map[string]any) (*hydration.Loaded, error) {
	return &hydration.Loaded{Program: l.program}, nil
}

func TestMarkdownGenerationRemovesUnsharedFieldsAndCachesRequirements(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	access := accessValue{"permissions": []any{"analytics:read", "program:read", "sessions:read"}, "granted_permissions": []any{"program:read", "sessions:read"}}
	cached := &testCache{}
	svc := New(registry, access, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	svc.Now = func() time.Time { return time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC) }
	svc.Cache = cached
	svc.Programs = testLoader{program: map[string]any{"meta": map[string]any{"program_name": "Test", "sex": "female", "block_notes": []any{map[string]any{"private": true, "text": "very secret"}, map[string]any{"text": "shared"}}}, "sessions": []any{}, "settings": map[string]any{"sex": "female"}}}
	result, err := svc.Call(context.Background(), "get_analysis_markdown", map[string]any{}, auth.Caller{Person: "coach", Athlete: "athlete"})
	if err != nil {
		t.Fatal(err)
	}
	document := result.(map[string]any)["markdown"].(string)
	if strings.Contains(document, "very secret") || strings.Contains(document, "female") {
		t.Fatalf("private data leaked: %s", document)
	}
	if cached.written == nil || cached.written["access_requirements"] == nil {
		t.Fatalf("missing cache requirements: %#v", cached.written)
	}
}
