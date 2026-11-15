package service

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	"powerlifting/sessions/internal/auth"
	"powerlifting/sessions/internal/contract"
	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/store"
	"powerlifting/sessions/internal/value"
)

type fakeAccess struct {
	access map[string]any
	status error
	hits   int
}

func (f *fakeAccess) Fetch(_ context.Context, _ string, _ map[string]any, caller auth.Caller) (map[string]any, error) {
	f.hits++
	if f.access == nil || f.status != nil {
		return f.access, f.status
	}
	access := map[string]any{"athlete_pk": caller.Athlete}
	for key, value := range f.access {
		access[key] = value
	}
	return access, nil
}

type recordedVersions struct {
	mu   sync.Mutex
	keys []string
}

func (r *recordedVersions) Bump(_ context.Context, athlete string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.keys = append(r.keys, store.VersionKey(athlete))
}

type harness struct {
	svc      *Service
	memory   *store.Memory
	access   *fakeAccess
	versions *recordedVersions
	counter  int
}

func newHarness(t *testing.T, access map[string]any) *harness {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	h := &harness{memory: store.NewMemory(), access: &fakeAccess{access: access}, versions: &recordedVersions{}}
	sessions := &session.Service{
		Sessions:    h.memory,
		Programs:    h.memory,
		SourceTable: "if-health",
		Now:         func() time.Time { return time.Date(2026, 11, 14, 12, 0, 0, 123456000, time.UTC) },
		NewID: func() string {
			h.counter++
			return fmt.Sprintf("uuid-%04d", h.counter)
		},
	}
	h.svc, err = New(registry, h.access, sessions, h.versions)
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func (h *harness) call(name string, arguments map[string]any) (any, error) {
	return h.svc.Call(context.Background(), name, arguments, auth.Caller{Person: "person", Athlete: "athlete"})
}

type scenario struct {
	Name    string         `json:"name"`
	Op      string         `json:"op"`
	Args    map[string]any `json:"args"`
	Athlete string         `json:"athlete"`
	Access  map[string]any `json:"access"`
	Seed    struct {
		Sessions []map[string]any `json:"sessions"`
		Health   []map[string]any `json:"health"`
	} `json:"seed"`
	Expect struct {
		OK            bool             `json:"ok"`
		Result        any              `json:"result"`
		Status        int              `json:"status"`
		Code          string           `json:"code"`
		Message       string           `json:"message"`
		SessionsAfter []map[string]any `json:"sessions_after"`
		Increments    []string         `json:"increments"`
	} `json:"expect"`
}

func loadScenarios(t *testing.T) []scenario {
	t.Helper()
	raw, err := os.ReadFile(goldenPath(t, "scenarios.json"))
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := value.Decode(raw)
	if err != nil {
		t.Fatal(err)
	}
	reencoded, _ := json.Marshal(decoded)
	var out []scenario
	decoder := json.NewDecoder(bytesReader(reencoded))
	decoder.UseNumber()
	if err := decoder.Decode(&out); err != nil {
		t.Fatal(err)
	}
	return out
}
