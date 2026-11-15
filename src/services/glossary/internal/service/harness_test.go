package service

import (
	"context"
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"

	"powerlifting/glossary/internal/apperr"
	"powerlifting/glossary/internal/athlete"
	"powerlifting/glossary/internal/auth"
	"powerlifting/glossary/internal/cache"
	"powerlifting/glossary/internal/coach"
	"powerlifting/glossary/internal/contract"
	"powerlifting/glossary/internal/execution"
	"powerlifting/glossary/internal/generic"
	"powerlifting/glossary/internal/store"
)

type fakeAccess struct {
	mu   sync.Mutex
	deny int
	seen []string
}

func (f *fakeAccess) Fetch(_ context.Context, operation string, _ map[string]any, _ auth.Caller) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.seen = append(f.seen, operation)
	if f.deny != 0 {
		return apperr.AccessDenied(f.deny)
	}
	return nil
}

type fakeCoach struct {
	mu          sync.Mutex
	submissions []coach.Submission
	fail        error
}

func (f *fakeCoach) Submit(_ context.Context, submission coach.Submission) (coach.Job, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.submissions = append(f.submissions, submission)
	if f.fail != nil {
		return coach.Job{}, f.fail
	}
	return coach.Job{ID: "job_1", Status: "running"}, nil
}

type fakeReader struct{ program athlete.Program }

func (f fakeReader) Program(context.Context, string) (athlete.Program, error) { return f.program, nil }

func (f fakeReader) Instances(context.Context, string, athlete.Program, string) ([]map[string]any, error) {
	return []map[string]any{{"date": "2026-01-01", "kg": 100.0}}, nil
}

type harness struct {
	svc    *Service
	store  *store.Memory
	coach  *fakeCoach
	access *fakeAccess
	redis  *miniredis.Miniredis
	valkey cache.Valkey
}

var clock = time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC)

func newHarness(t *testing.T) *harness {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	server := miniredis.RunT(t)
	valkey := cache.Valkey{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	h := &harness{store: store.NewMemory(), coach: &fakeCoach{}, access: &fakeAccess{}, redis: server, valkey: valkey}
	now := func() time.Time { return clock }
	program := athlete.Program{SK: "program#v001", Meta: map[string]any{"height_cm": 180.0}, LiftProfiles: []map[string]any{{"lift": "squat", "options": map[string]any{"bar_position": "low"}, "volume_tolerance": "high"}}}
	h.svc, err = New(&Service{
		Registry: registry, Access: h.access, Store: h.store, Athletes: fakeReader{program: program}, Coach: h.coach,
		Executions: execution.New(cache.Prompts{Valkey: valkey, Now: now}), Generic: &generic.Estimator{Store: h.store, Coach: h.coach, Interval: time.Minute, Now: now},
		Cache: valkey, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	return h
}

var person = auth.Caller{Person: "p1", Athlete: "a1"}

func (h *harness) call(t *testing.T, name string, arguments map[string]any) map[string]any {
	t.Helper()
	response, err := h.svc.Call(context.Background(), name, arguments, person)
	if err != nil {
		t.Fatalf("%s: %v", name, err)
	}
	body, _ := response.Body.(map[string]any)
	return body
}

func (h *harness) fail(t *testing.T, name string, arguments map[string]any, status int) {
	t.Helper()
	_, err := h.svc.Call(context.Background(), name, arguments, person)
	var failure *apperr.Error
	if err == nil || !asApp(err, &failure) || failure.Status != status {
		t.Fatalf("%s: want status %d, got %v", name, status, err)
	}
}

func asApp(err error, target **apperr.Error) bool {
	failure, ok := err.(*apperr.Error)
	*target = failure
	return ok
}

func (h *harness) seedCatalog(t *testing.T, id, name string, extra map[string]any) {
	t.Helper()
	item := map[string]any{"id": id, "name": name, "name_key": strings.ToLower(name), "created_at": "2026-01-01T00:00:00Z", "generic_status": "ready", "created_by": "a2"}
	for key, value := range extra {
		item[key] = value
	}
	if created, err := h.store.CreateCatalog(context.Background(), item); err != nil || !created {
		t.Fatalf("seed %s: %v", id, err)
	}
}

func (h *harness) overlay(t *testing.T, athleteID, id string) map[string]any {
	t.Helper()
	item, err := h.store.Get(context.Background(), store.OverlayKey(athleteID, id))
	if err != nil {
		t.Fatal(err)
	}
	return item
}

func (h *harness) catalog(t *testing.T, id string) map[string]any {
	t.Helper()
	item, err := h.store.Get(context.Background(), store.CatalogKey(id))
	if err != nil {
		t.Fatal(err)
	}
	return item
}

func (h *harness) drive(t *testing.T, name string, arguments map[string]any, caller auth.Caller, answers ...map[string]any) (map[string]any, []map[string]any) {
	t.Helper()
	caller.JobID = "job_1"
	response, err := h.svc.Call(context.Background(), name, arguments, caller)
	var asked []map[string]any
	for {
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		body := response.Body.(map[string]any)
		switch body["status"] {
		case "succeeded":
			return body["result"].(map[string]any), asked
		case "needs_inference":
			if len(answers) == 0 {
				t.Fatalf("%s asked for more inference than answered: %v", name, body["tools"])
			}
			asked = append(asked, body)
			response, err = h.svc.Resume(context.Background(), body["execution_id"].(string), map[string]any{"challenge_id": body["challenge_id"], "content": answers[0]}, caller)
			answers = answers[1:]
		default:
			response, err = h.svc.Resume(context.Background(), body["execution_id"].(string), map[string]any{}, caller)
		}
	}
}

func toolName(challenge map[string]any) string {
	tools, _ := challenge["tools"].([]any)
	tool, _ := tools[0].(map[string]any)
	function, _ := tool["function"].(map[string]any)
	name, _ := function["name"].(string)
	return name
}

func prompt(challenge map[string]any) string {
	encoded, _ := json.Marshal(challenge["messages"])
	return string(encoded)
}

var errTest = &apperr.Error{Status: 502, Code: "execution_failed", Message: "coach down"}
