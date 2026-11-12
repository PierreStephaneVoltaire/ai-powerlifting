package service

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"google.golang.org/protobuf/types/known/structpb"

	analyticsv1 "powerlifting/analytics-ai/gen/analytics"
	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/cache"
	"powerlifting/analytics-ai/internal/coach"
	"powerlifting/analytics-ai/internal/contract"
	"powerlifting/analytics-ai/internal/data"
	"powerlifting/analytics-ai/internal/execution"
	"powerlifting/analytics-ai/internal/generation"
)

type fakeAccess struct {
	mu     sync.Mutex
	calls  []string
	deny   int
	access auth.Access
}

func (f *fakeAccess) Fetch(_ context.Context, operation string, _ map[string]any, caller auth.Caller) (auth.Access, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, operation)
	if f.deny != 0 {
		return nil, apperr.AccessDenied(f.deny)
	}
	access := auth.Access{"person_pk": caller.Person, "settings_pk": caller.Person, "is_self": true, "permissions": []any{"analytics:read", "analytics:write"}}
	for key, value := range f.access {
		access[key] = value
	}
	return access, nil
}

func mustStruct(value map[string]any) *structpb.Struct {
	result, err := structpb.NewStruct(value)
	if err != nil {
		panic(err)
	}
	return result
}

type fakeSource struct {
	mu          sync.Mutex
	blocks      []map[string]any
	compare     map[string]any
	lifetime    map[string]any
	correlation *analyticsv1.CorrelationInputsReply
	snapshot    *analyticsv1.Snapshot
	principals  []data.Principal
}

func (f *fakeSource) record(p data.Principal) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.principals = append(f.principals, p)
}

func (f *fakeSource) Blocks(_ context.Context, p data.Principal) ([]map[string]any, error) {
	f.record(p)
	return f.blocks, nil
}

func (f *fakeSource) Bundle(_ context.Context, p data.Principal, key string) (map[string]any, error) {
	f.record(p)
	return map[string]any{"block": map[string]any{"blockKey": key}, "weekly": map[string]any{"fatigue_index": 1.5}, "sourceFingerprint": "fp-" + key}, nil
}

func (f *fakeSource) Compare(_ context.Context, p data.Principal, _ []string) (map[string]any, error) {
	f.record(p)
	return f.compare, nil
}

func (f *fakeSource) Lifetime(_ context.Context, p data.Principal) (map[string]any, error) {
	f.record(p)
	return f.lifetime, nil
}

func (f *fakeSource) Correlation(_ context.Context, p data.Principal, _ string) (*analyticsv1.CorrelationInputsReply, error) {
	f.record(p)
	return f.correlation, nil
}

func (f *fakeSource) Snapshot(_ context.Context, p data.Principal) (*analyticsv1.Snapshot, error) {
	f.record(p)
	return f.snapshot, nil
}

type fakeExporter struct {
	mu      sync.Mutex
	reports []data.LifetimeReport
}

func (f *fakeExporter) SaveLifetimeReport(_ context.Context, _ data.Principal, report data.LifetimeReport) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.reports = append(f.reports, report)
	return nil
}

type stubCoach struct {
	server    *httptest.Server
	mu        sync.Mutex
	submitted []submission
	jobStatus string
	jobError  any
	reject    int
}

type submission struct {
	Header http.Header
	Body   map[string]any
}

func newStubCoach(t *testing.T) *stubCoach {
	stub := &stubCoach{jobStatus: "running"}
	stub.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		stub.mu.Lock()
		defer stub.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		if r.Method == http.MethodGet {
			_ = json.NewEncoder(w).Encode(map[string]any{"job_id": strings.TrimPrefix(r.URL.Path, "/v1/jobs/"), "status": stub.jobStatus, "error": stub.jobError})
			return
		}
		raw, _ := io.ReadAll(r.Body)
		var body map[string]any
		_ = json.Unmarshal(raw, &body)
		if stub.reject != 0 {
			w.WriteHeader(stub.reject)
			_, _ = w.Write([]byte("rejected"))
			return
		}
		stub.submitted = append(stub.submitted, submission{Header: r.Header.Clone(), Body: body})
		_ = json.NewEncoder(w).Encode(map[string]any{"job_id": "job_" + string(rune('0'+len(stub.submitted))), "status": "running"})
	}))
	t.Cleanup(stub.server.Close)
	return stub
}

func (s *stubCoach) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.submitted)
}

type harness struct {
	svc      *Service
	access   *fakeAccess
	source   *fakeSource
	coach    *stubCoach
	exporter *fakeExporter
	backend  *generation.Memory
	redis    *miniredis.Miniredis
	clock    *time.Time
}

func weekly(week int, squat, bench, deadlift float64) *analyticsv1.WeeklyE1Rm {
	return &analyticsv1.WeeklyE1Rm{WeekNumber: int32(week), SquatKg: &squat, BenchKg: &bench, DeadliftKg: &deadlift}
}

func newHarness(t *testing.T) *harness {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	clock := time.Date(2026, 11, 12, 10, 0, 0, 0, time.UTC)
	server := miniredis.RunT(t)
	kv := cache.Redis{Client: redis.NewClient(&redis.Options{Addr: server.Addr()})}
	stub := newStubCoach(t)
	h := &harness{access: &fakeAccess{}, coach: stub, exporter: &fakeExporter{}, backend: generation.NewMemory(), redis: server, clock: &clock}
	h.source = &fakeSource{
		blocks: []map[string]any{
			{"blockKey": "block_1", "label": "Block 1", "isCurrent": false, "startDate": "2026-01-05", "endDate": "2026-03-01", "weekCount": float64(8), "phases": []any{}},
			{"blockKey": "block_short", "label": "Short", "isCurrent": false, "startDate": "2026-04-05", "endDate": "2026-04-20", "weekCount": float64(2), "phases": []any{}},
			{"blockKey": "current", "label": "Current", "isCurrent": true, "startDate": "2026-09-01", "endDate": "", "weekCount": float64(10), "phases": []any{}},
		},
		compare: map[string]any{
			"schemaVersion": float64(6), "generatedAt": "2026-11-12T10:00:00Z", "selectedBlockKeys": []any{"block_1", "current"},
			"rows":   []any{map[string]any{"blockKey": "block_1", "competitions": []any{}, "goals": []any{}}},
			"trends": map[string]any{}, "roiSignals": []any{}, "exerciseRoi": []any{}, "correlationFindings": []any{}, "patternSignals": []any{},
			"liftDoseResponse": []any{}, "trainingDayResponse": []any{}, "volumeTolerance": map[string]any{}, "missingDataSummary": []any{},
		},
		lifetime: map[string]any{"athlete": "athlete_1", "blocks": []any{}},
		correlation: &analyticsv1.CorrelationInputsReply{
			BlockKey: "block_1", WindowStart: "2026-01-05", Weeks: 8,
			WeeklyE1Rm: []*analyticsv1.WeeklyE1Rm{weekly(1, 180, 120, 220), weekly(2, 182, 121, 222), weekly(3, 184, 122, 224), weekly(4, 186, 123, 226), weekly(5, 188, 124, 228)},
			WeeklyAccessory: []*analyticsv1.WeeklyAccessoryVolume{
				{WeekNumber: 1, Exercises: []*analyticsv1.ExerciseVolume{{Name: "Leg Press", VolumeKg: 2000}}},
				{WeekNumber: 2, Exercises: []*analyticsv1.ExerciseVolume{{Name: "Leg Press", VolumeKg: 2200}}},
			},
			AthleteMeasurements: mustStruct(map[string]any{"height_cm": 180}),
		},
		snapshot: &analyticsv1.Snapshot{Program: mustStruct(map[string]any{"meta": map[string]any{"name": "Program"}, "phases": []any{}})},
	}
	for week := 1; week <= 5; week++ {
		date := time.Date(2026, 1, 5, 0, 0, 0, 0, time.UTC).AddDate(0, 0, 7*(week-1)).Format("2006-01-02")
		h.source.snapshot.Sessions = append(h.source.snapshot.Sessions, mustStruct(map[string]any{"date": date, "week_number": float64(week), "completed": true, "exercises": []any{map[string]any{"name": "Squat", "sets": float64(3), "reps": float64(5), "kg": float64(150)}}}))
	}
	manager := execution.New(cache.Prompts{KV: kv})
	h.svc = &Service{
		Registry: registry, Access: h.access, Coach: coach.HTTP{URL: stub.server.URL, Client: stub.server.Client()}, Source: h.source,
		Exporter: h.exporter, KV: kv, Backend: h.backend, Executions: manager, Now: func() time.Time { return clock },
	}
	return h
}

func person() auth.Caller {
	return auth.Caller{Person: "person_1", Athlete: "athlete_1", Source: "spiffe://cluster.local/ns/pl/sa/powerlifting-app-backend"}
}

func inCoachJob(caller auth.Caller, generationID string, attempt int) auth.Caller {
	caller.JobID, caller.TurnID = "job_1", "turn_1"
	if generationID != "" {
		caller.Generation = &auth.Generation{ID: generationID, Attempt: attempt}
	}
	return caller
}

func (h *harness) call(t *testing.T, name string, arguments map[string]any, caller auth.Caller) (Response, error) {
	t.Helper()
	if arguments == nil {
		arguments = map[string]any{}
	}
	return h.svc.Call(context.Background(), name, arguments, caller)
}

func asMap(t *testing.T, value any) map[string]any {
	t.Helper()
	object, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("expected an object, got %T", value)
	}
	return object
}
