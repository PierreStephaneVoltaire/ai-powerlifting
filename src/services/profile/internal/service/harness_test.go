package service

import (
	"context"
	"fmt"
	"math/big"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"powerlifting/profile/internal/auth"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/fakedb"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var tableNames = map[string]string{
	"user": "if-user", "requests": "if-powerlifting-requests", "notifications": "if-powerlifting-notifications",
	"tags": "if-powerlifting-tags", "health": "if-health", "sessions": "if-sessions",
	"competitions": "if-powerlifting-user-competitions", "videos": "workout-Videos",
}

func schema() map[string]fakedb.Schema {
	return map[string]fakedb.Schema{
		"if-user":                           {Hash: "pk"},
		"if-powerlifting-requests":          {Hash: "pk", Range: "sk", Indexes: map[string]fakedb.Index{"InboxIndex": {Hash: "inbox_pk", Range: "inbox_sk"}, "SentIndex": {Hash: "sent_pk", Range: "sent_sk"}, "RosterIndex": {Hash: "roster_pk", Range: "roster_sk"}}},
		"if-powerlifting-notifications":     {Hash: "pk", Range: "sk"},
		"if-powerlifting-tags":              {Hash: "pk", Range: "sk"},
		"if-health":                         {Hash: "pk", Range: "sk"},
		"if-sessions":                       {Hash: "pk", Range: "sk"},
		"if-powerlifting-user-competitions": {Hash: "pk", Range: "sk"},
		"workout-Videos":                    {Hash: "athlete_id", Range: "video_id"},
	}
}

func tables() store.Tables {
	return store.Tables{
		User: "if-user", Requests: "if-powerlifting-requests", Notifications: "if-powerlifting-notifications", Tags: "if-powerlifting-tags",
		Health: "if-health", Sessions: "if-sessions", Competitions: "if-powerlifting-user-competitions", Videos: "workout-Videos",
		SentIndex: "SentIndex", InboxIndex: "InboxIndex", RosterIndex: "RosterIndex",
	}
}

type bumps struct {
	mu   sync.Mutex
	keys []string
}

func (b *bumps) Bump(_ context.Context, athlete string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.keys = append(b.keys, store.VersionKey(athlete))
}

type discord map[string]string

func (d discord) Avatar(_ context.Context, userID string) string { return d[userID] }

type analytics map[string]any

func (a analytics) EstimatedMaxes(context.Context, string, string) map[string]any { return a }

type s3Object struct {
	ContentType string
	Metadata    map[string]string
	Size        int
}

type bucket struct {
	mu      sync.Mutex
	objects map[string]s3Object
}

func (b *bucket) Put(_ context.Context, key, contentType string, body []byte, metadata map[string]string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.objects[key] = s3Object{ContentType: contentType, Metadata: metadata, Size: len(body)}
	return nil
}

func (b *bucket) Delete(_ context.Context, key string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	delete(b.objects, key)
	return nil
}

func (b *bucket) listing() []any {
	keys := make([]string, 0, len(b.objects))
	for key := range b.objects {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	out := make([]any, len(keys))
	for i, key := range keys {
		entry := b.objects[key]
		metadata := map[string]any{}
		for k, v := range entry.Metadata {
			metadata[k] = v
		}
		out[i] = map[string]any{"key": key, "content_type": entry.ContentType, "metadata": metadata, "size": value.Int(entry.Size)}
	}
	return out
}

type harness struct {
	svc     *Service
	db      *fakedb.DB
	bumps   *bumps
	bucket  *bucket
	now     time.Time
	ids     []string
	counter int
}

func parseStamp(t testing.TB, text string) time.Time {
	t.Helper()
	parsed, err := time.Parse("2006-01-02T15:04:05.999999999Z07:00", text)
	if err != nil {
		t.Fatalf("bad time %q: %v", text, err)
	}
	return parsed
}

func defaultID(n int) string {
	base, _ := new(big.Int).SetString("abc000000000000000000000000000", 16)
	base.Add(base, big.NewInt(int64(n)))
	return fmt.Sprintf("%032x", base)
}

type options struct {
	Now       string
	IDs       []string
	Discord   map[string]string
	Analytics map[string]any
	S3Seed    []string
}

func newHarness(t testing.TB, opts options) *harness {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	h := &harness{db: fakedb.New(schema()), bumps: &bumps{}, bucket: &bucket{objects: map[string]s3Object{}}, ids: opts.IDs}
	h.now = parseStamp(t, "2026-11-14T12:00:00.123456+00:00")
	if opts.Now != "" {
		h.now = parseStamp(t, opts.Now)
	}
	for _, key := range opts.S3Seed {
		h.bucket.objects[key] = s3Object{ContentType: "image/png", Metadata: map[string]string{}, Size: 3}
	}
	env := clock.Env{
		Now: func() time.Time { return h.now },
		ID: func() string {
			if len(h.ids) > 0 {
				id := h.ids[0]
				h.ids = h.ids[1:]
				return id
			}
			h.counter++
			return defaultID(h.counter)
		},
	}
	var maxes Analytics
	if opts.Analytics != nil {
		maxes = analytics(opts.Analytics)
	}
	h.svc, err = New(Deps{
		Registry: registry, DB: &store.DB{API: h.db, Tables: tables()}, Env: env, Versions: h.bumps,
		Discord: discord(opts.Discord), Analytics: maxes, Avatars: h.bucket,
	})
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func (h *harness) seed(logical string, items ...value.Item) {
	h.db.Seed(tableNames[logical], items...)
}

func (h *harness) call(op string, args map[string]any, caller auth.Caller) (any, error) {
	return h.svc.Call(context.Background(), op, args, caller)
}

func caller(person, athlete string) auth.Caller { return auth.Caller{Person: person, Athlete: athlete} }

func ids(values ...string) []string { return values }

var _ = strings.TrimSpace
