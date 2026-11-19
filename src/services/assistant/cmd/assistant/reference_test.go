package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"powerlifting/assistant/internal/config"
	"testing"
)

func TestReferenceClientNeverFallsBackToRegularGateway(t *testing.T) {
	regularCalls, privateCalls := 0, 0
	regular := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		regularCalls++
		t.Error("ordinary gateway received a private request")
	}))
	defer regular.Close()
	private := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		privateCalls++
		fmt.Fprint(w, `{"data":[{"index":0,"embedding":[1]}]}`)
	}))
	defer private.Close()
	cfg := config.Config{LiteLLMBaseURL: regular.URL, ReferenceLiteLLMURL: private.URL, ReferenceLiteLLMKey: "private"}
	client := referenceClient(cfg)
	if _, err := client.EmbedPrivate(context.Background(), "embed", "secret"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.EmbedPrivateBatch(context.Background(), "embed", []string{"secret"}); err != nil {
		t.Fatal(err)
	}
	if regularCalls != 0 || privateCalls != 2 {
		t.Fatalf("regular=%d private=%d", regularCalls, privateCalls)
	}
	cfg.ReferenceLiteLLMURL = regular.URL
	if referenceClient(cfg) != nil {
		t.Fatal("ordinary endpoint accepted as private")
	}
	cfg.ReferenceLiteLLMURL = ""
	if referenceClient(cfg) != nil {
		t.Fatal("missing endpoint accepted")
	}
}
