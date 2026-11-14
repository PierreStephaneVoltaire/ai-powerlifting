package cache

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newValkey(t *testing.T) (Valkey, *miniredis.Miniredis) {
	server := miniredis.RunT(t)
	return Valkey{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}, server
}

func TestExactCacheKeyedByAthleteOperationAndRequest(t *testing.T) {
	valkey, _ := newValkey(t)
	ctx := context.Background()
	request := Request{Messages: []any{"m"}}
	valkey.Remember(ctx, "a1", "op", request, map[string]any{"ok": true})
	if _, hit := valkey.Exact(ctx, "a1", "op", request); !hit {
		t.Fatal("miss for same key")
	}
	if _, hit := valkey.Exact(ctx, "a2", "op", request); hit {
		t.Fatal("hit across athletes")
	}
	if _, hit := valkey.Exact(ctx, "a1", "op", Request{Messages: []any{"other"}}); hit {
		t.Fatal("hit for different request")
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
