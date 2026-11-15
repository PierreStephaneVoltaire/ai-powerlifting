package cache

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newValkey(t *testing.T) (Valkey, *miniredis.Miniredis) {
	server := miniredis.RunT(t)
	return Valkey{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}, server
}

func TestPromptsSendAthleteVersionAndDateAndTreatErrorsAsMiss(t *testing.T) {
	valkey, server := newValkey(t)
	server.Set("pl:analysis-version:a1", "7")
	var seen []promptBody
	api := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body promptBody
		_ = json.NewDecoder(r.Body).Decode(&body)
		seen = append(seen, body)
		if r.URL.Path == "/lookup" {
			_, _ = w.Write([]byte(`{"hit":true,"layer":"exact","response":{"ok":true}}`))
		}
	}))
	defer api.Close()
	now := func() time.Time { return time.Date(2026, 11, 14, 1, 0, 0, 0, time.UTC) }
	prompts := Prompts{Valkey: valkey, URL: api.URL, Now: now}
	request := Request{Messages: []any{"m"}}
	response, layer, hit := prompts.Lookup(context.Background(), "a1", "op", request)
	if !hit || layer != "exact" || response["ok"] != true {
		t.Fatalf("lookup %v %q %v", response, layer, hit)
	}
	prompts.Remember(context.Background(), "a1", "op", request, map[string]any{"ok": true})
	if len(seen) != 2 || seen[0].Context.AnalysisVersion != "7" || seen[0].Context.Date != "2026-11-14" || seen[1].Athlete != "a1" || seen[1].Response == nil {
		t.Fatalf("seen %+v", seen)
	}
	api.Close()
	if _, _, hit := prompts.Lookup(context.Background(), "a1", "op", request); hit {
		t.Fatal("unreachable cache service was a hit")
	}
	if _, _, hit := (Prompts{Valkey: valkey}).Lookup(context.Background(), "a1", "op", request); hit {
		t.Fatal("unconfigured cache was a hit")
	}
}

func TestInvalidateCatalogSweepsAnalysisKeysAndBumpsEveryVersion(t *testing.T) {
	valkey, server := newValkey(t)
	server.Set("pl:analysis:a1:section:x", "{}")
	server.Set("pl:analysis:a2:section:y", "{}")
	server.Set("pl:analysis-version:a1", "3")
	server.Set("pl:analysis-version:a2", "9")
	server.Set("pl:analysis-build", "b1")
	valkey.InvalidateCatalog(context.Background())
	if server.Exists("pl:analysis:a1:section:x") || server.Exists("pl:analysis:a2:section:y") {
		t.Fatal("analysis keys survived")
	}
	if !server.Exists("pl:analysis-build") {
		t.Fatal("build marker swept")
	}
	if a1, _ := server.Get("pl:analysis-version:a1"); a1 != "4" {
		t.Fatalf("a1 version %q", a1)
	}
	if a2, _ := server.Get("pl:analysis-version:a2"); a2 != "10" {
		t.Fatalf("a2 version %q", a2)
	}
}

func TestInvalidateAllGlossariesClearsEveryAthlete(t *testing.T) {
	valkey, server := newValkey(t)
	for _, athlete := range []string{"a1", "a2"} {
		item := "pl:cache:" + athlete + ":item:u"
		server.Set(item, "{}")
		server.Set("pl:cache:"+athlete+":idx:u", "x")
		server.SAdd("pl:cache:"+athlete+":domain:glossary", item)
	}
	server.Set("pl:cache:a1:item:keep", "{}")
	valkey.InvalidateAllGlossaries(context.Background())
	for _, athlete := range []string{"a1", "a2"} {
		if server.Exists("pl:cache:"+athlete+":item:u") || server.Exists("pl:cache:"+athlete+":idx:u") || server.Exists("pl:cache:"+athlete+":domain:glossary") {
			t.Fatalf("%s cache survived", athlete)
		}
	}
	if !server.Exists("pl:cache:a1:item:keep") {
		t.Fatal("unrelated cache dropped")
	}
}
