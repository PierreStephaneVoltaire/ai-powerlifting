package testenv

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/contract"
	"powerlifting/profile/internal/fakedb"
	"powerlifting/profile/internal/service"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var Schema = map[string]fakedb.Schema{
	"if-user":                           {Hash: "pk"},
	"if-powerlifting-requests":          {Hash: "pk", Range: "sk", Indexes: map[string]fakedb.Index{"InboxIndex": {Hash: "inbox_pk", Range: "inbox_sk"}, "SentIndex": {Hash: "sent_pk", Range: "sent_sk"}, "RosterIndex": {Hash: "roster_pk", Range: "roster_sk"}}},
	"if-powerlifting-notifications":     {Hash: "pk", Range: "sk"},
	"if-powerlifting-tags":              {Hash: "pk", Range: "sk"},
	"if-health":                         {Hash: "pk", Range: "sk"},
	"if-sessions":                       {Hash: "pk", Range: "sk"},
	"if-powerlifting-user-competitions": {Hash: "pk", Range: "sk"},
	"workout-Videos":                    {Hash: "athlete_id", Range: "video_id"},
}

var Tables = store.Tables{
	User: "if-user", Requests: "if-powerlifting-requests", Notifications: "if-powerlifting-notifications", Tags: "if-powerlifting-tags",
	Health: "if-health", Sessions: "if-sessions", Competitions: "if-powerlifting-user-competitions", Videos: "workout-Videos",
	SentIndex: "SentIndex", InboxIndex: "InboxIndex",
}

type Bumps struct {
	mu   sync.Mutex
	Keys []string
}

func (b *Bumps) Bump(_ context.Context, athlete string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.Keys = append(b.Keys, store.VersionKey(athlete))
}

type Env struct {
	Service *service.Service
	DB      *fakedb.DB
	Bumps   *Bumps
	Now     time.Time
	counter int
}

func New(t testing.TB) *Env {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	e := &Env{DB: fakedb.New(Schema), Bumps: &Bumps{}, Now: time.Date(2026, 11, 14, 12, 0, 0, 123456000, time.UTC)}
	env := clock.Env{
		Now: func() time.Time { return e.Now },
		ID: func() string {
			e.counter++
			return fmt.Sprintf("%032x", e.counter)
		},
	}
	e.Service, err = service.New(service.Deps{Registry: registry, DB: &store.DB{API: e.DB, Tables: Tables}, Env: env, Versions: e.Bumps})
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func (e *Env) Seed(table string, items ...value.Item) { e.DB.Seed(table, items...) }
