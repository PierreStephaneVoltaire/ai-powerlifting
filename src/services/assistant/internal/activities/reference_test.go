package activities

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"powerlifting/assistant/internal/llm"
	"powerlifting/assistant/internal/reference"
)

type referenceStub struct{ passages []reference.Passage }

func (s referenceStub) Search(_ context.Context, _ reference.SearchRequest) ([]reference.Passage, error) {
	return s.passages, nil
}

func TestReferenceLookupRejectsInconsistentCoverageAndRecitation(t *testing.T) {
	editionDate := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	passage := "The secret sentence contains several words that should never appear in durable results."
	for _, test := range []struct {
		answer string
		want   string
	}{
		{`{"coverage":"full","finding":"A safe paraphrase.","gap":""}`, "full"},
		{`{"coverage":"partial","finding":"A safe paraphrase.","gap":""}`, "none"},
		{`{"coverage":"none","finding":"A safe paraphrase.","gap":"unknown"}`, "none"},
		{`{"coverage":"full","finding":"The secret sentence contains several words that should never appear","gap":""}`, "none"},
	} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, _ := io.ReadAll(r.Body)
			b := string(body)
			if !strings.Contains(b, "Edition: 2026") || !strings.Contains(b, "2026-01-01") {
				t.Error("edition metadata missing")
			}
			if !strings.Contains(b, `"response_format":{"type":"json_object"}`) || !strings.Contains(b, `"reasoning_effort":"none"`) {
				t.Error("reference reader must request JSON with reasoning disabled")
			}
			fmt.Fprintf(w, `{"choices":[{"message":{"content":%q}}]}`, test.answer)
		}))
		deps := Deps{Reference: referenceStub{[]reference.Passage{{Text: passage, Edition: "2026", EffectiveDate: &editionDate}}}, ReferenceLLM: llm.New(server.URL, "key"), Slots: make(chan struct{}, 1)}
		result, err := deps.ReferenceLookup(context.Background(), ReferenceLookupInput{Collection: "federations", Scope: "federation:ipf", Query: "rules?"})
		server.Close()
		if err != nil || result.Coverage != test.want {
			t.Fatalf("result: %+v, %v", result, err)
		}
	}
}

func TestReferenceMissDoesNotReturnContextOrUseOrdinaryModel(t *testing.T) {
	regular := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("ordinary model was called") }))
	defer regular.Close()
	private := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		fmt.Fprint(w, "secret-history-marker")
	}))
	defer private.Close()
	var logs bytes.Buffer
	deps := Deps{Reference: referenceStub{[]reference.Passage{{Text: "reference text"}}}, LLM: llm.New(regular.URL, "key"), ReferenceLLM: llm.New(private.URL, "private"), Slots: make(chan struct{}, 1), Log: slog.New(slog.NewJSONHandler(&logs, nil))}
	result, err := deps.ReferenceLookup(context.Background(), ReferenceLookupInput{Collection: "supplements", Scope: "supplements", Query: "Is creatine useful?", Context: "secret-history-marker"})
	if err != nil || result.Gap != "Is creatine useful?" || strings.Contains(fmt.Sprint(result), "secret-history-marker") {
		t.Fatalf("unsafe miss: %+v %v", result, err)
	}
	if output := logs.String(); !strings.Contains(output, `"failed":true,"stage":"reader"`) || strings.Contains(output, "reference text") || strings.Contains(output, "secret-history-marker") || strings.Contains(output, "Is creatine useful?") {
		t.Fatal("lookup log must contain the failure stage and omit passages, conversation context and query")
	}
}
