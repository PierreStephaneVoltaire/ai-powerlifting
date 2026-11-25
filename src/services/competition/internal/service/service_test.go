package service

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/auth"
	"powerlifting/competition/internal/contract"
	"powerlifting/competition/internal/store"
)

type failingVersions struct{ calls int }

func (f *failingVersions) Bump(context.Context, string) error {
	f.calls++
	return errors.New("valkey down")
}

func build(t *testing.T, memory *store.Memory, versions store.AnalysisVersions) *Service {
	t.Helper()
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	now := func() time.Time { return time.Date(2027, 4, 24, 12, 0, 0, 0, time.UTC) }
	svc, err := New(registry, &fakeAccess{}, memory, memory, versions, now, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	return svc
}

func call(svc *Service, operation string, arguments map[string]any) (any, error) {
	return svc.Call(context.Background(), operation, arguments, auth.Caller{Person: person, Athlete: athlete})
}

func TestACacheOutageDoesNotFailAWrite(t *testing.T) {
	memory := store.NewMemory()
	memory.Load("entries", []store.Item{{"pk": athlete, "sk": "COMP#m", "user_status": "available"}})
	versions := &failingVersions{}
	svc := build(t, memory, versions)
	result, err := call(svc, "health_update_user_competition", map[string]any{"master_id": "m", "patch": map[string]any{"notes": "x"}})
	if err != nil || result.(map[string]any)["notes"] != "x" || versions.calls != 1 {
		t.Fatalf("%v %v %d", result, err, versions.calls)
	}
}

func TestReadsNeverTouchTheAnalysisVersion(t *testing.T) {
	memory := store.NewMemory()
	versions := &failingVersions{}
	svc := build(t, memory, versions)
	if _, err := call(svc, "health_list_competitions", map[string]any{}); err != nil {
		t.Fatal(err)
	}
	if versions.calls != 0 {
		t.Fatal("list bumped the version")
	}
}

func TestProgramLookup(t *testing.T) {
	cases := []struct {
		name   string
		health []store.Item
		status int
		jump   any
	}{
		{"no program", nil, 404, nil},
		{"dangling pointer", []store.Item{{"pk": athlete, "sk": "program#current", "ref_sk": "program#v009"}}, 500, nil},
		{"pointer without ref", []store.Item{{"pk": athlete, "sk": "program#current", "version": 7}}, 404, nil},
		{"pointer ref", []store.Item{
			{"pk": athlete, "sk": "program#current", "ref_sk": "program#v007"},
			{"pk": athlete, "sk": "program#v007", "operator_prefs": map[string]any{"attempt_jumps": map[string]any{"squat": map[string]any{"j1": 15, "j2": 15}}}},
		}, 0, 15.0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			memory := store.NewMemory()
			memory.Load("health", tc.health)
			result, err := call(build(t, memory, memory), "calculate_attempts", map[string]any{"lift": "squat", "opener_kg": 100.0})
			if tc.status != 0 {
				var failure *apperr.Error
				if !errors.As(err, &failure) || failure.Status != tc.status {
					t.Fatalf("got %v, want status %d", err, tc.status)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			jumps := result.(map[string]any)["jumps_used"].(map[string]any)
			if got, _ := jumps["j1"].(interface{ Float64() (float64, error) }).Float64(); got != tc.jump {
				t.Fatalf("jumps %v", jumps)
			}
		})
	}
}

func TestSnapshotErrors(t *testing.T) {
	memory := store.NewMemory()
	svc := build(t, memory, memory)
	var failure *apperr.Error
	if _, err := call(svc, "health_snapshot_competition_projection", map[string]any{"date": "2027-4-24xx"}); !errors.As(err, &failure) || failure.Status != 422 {
		t.Fatalf("%v", err)
	}
	if _, err := call(svc, "health_snapshot_competition_projection", map[string]any{"date": "2027-04-24"}); !errors.As(err, &failure) || failure.Status != 404 {
		t.Fatalf("%v", err)
	}
}

func TestSnapshotWriteFailureSurfaces(t *testing.T) {
	memory := store.NewMemory()
	memory.Load("health", []store.Item{
		{"pk": athlete, "sk": "program#current", "ref_sk": "program#v001"},
		{"pk": athlete, "sk": "program#v001", "meta": map[string]any{"program_start": "2027-01-04", "current_body_weight_kg": 90.0}},
	})
	memory.Load("entries", []store.Item{
		{"pk": athlete, "sk": "COMP#m", "name": "M", "user_status": "completed", "start_date": "2027-03-01", "entry_date": "2027-03-01", "results": map[string]any{"squat_kg": 200.0}},
		{"pk": athlete, "sk": "COMP#t", "name": "T", "user_status": "confirmed", "start_date": "2027-05-01", "entry_date": "2027-05-01"},
	})
	var sessions []store.Item
	for week := range 8 {
		date := time.Date(2027, 1, 4, 0, 0, 0, 0, time.UTC).AddDate(0, 0, week*7+0)
		sessions = append(sessions, store.Item{
			"pk": athlete, "sk": "session#program#v001#" + date.Format("2006-01-02") + "#001#s", "date": date.Format("2006-01-02"),
			"week_number": float64(week + 1), "status": "completed", "completed": true,
			"exercises": []any{map[string]any{"name": "Squat", "sets": 4.0, "reps": 5.0, "kg": 140.0 + 2.5*float64(week)}},
		})
	}
	memory.Load("sessions", sessions)
	svc := build(t, memory, memory)
	result, err := call(svc, "health_snapshot_competition_projection", map[string]any{"date": "2027-04-24"})
	if err != nil {
		t.Fatal(err)
	}
	if updated := result.(map[string]any)["updated"]; updated != 1 {
		t.Fatalf("%v", result)
	}
	if memory.EntryItems[[2]string{athlete, "COMP#t"}]["projection_snapshot_date"] != "2027-04-24" {
		t.Fatalf("%v", memory.EntryItems[[2]string{athlete, "COMP#t"}])
	}
	memory.FailUpdate = errors.New("write failed")
	delete(memory.EntryItems[[2]string{athlete, "COMP#t"}], "projected_at_t_minus_1w")
	if _, err := call(svc, "health_snapshot_competition_projection", map[string]any{"date": "2027-04-24"}); err == nil {
		t.Fatal("write failure swallowed")
	}
}

func TestEveryCompetitionMutationBumpsTheAnalysisVersion(t *testing.T) {
	cases := []struct {
		name      string
		operation string
		arguments map[string]any
		bumps     int
	}{
		{"update operation", "health_update_user_competition", map[string]any{"master_id": "m", "patch": map[string]any{"notes": "x"}}, 1},
		{"complete operation", "health_complete_user_competition", map[string]any{"master_id": "m", "body_weight_kg": 90.0, "results": map[string]any{"squat_kg": 200.0}}, 1},
		{"list op update explicit", "health_list_competitions", map[string]any{"op": "update", "master_id": "m", "patch": map[string]any{"notes": "x"}}, 1},
		{"list op update inferred", "health_list_competitions", map[string]any{"master_id": "m", "patch": map[string]any{"notes": "x"}}, 1},
		{"list op complete explicit", "health_list_competitions", map[string]any{"op": "complete", "master_id": "m", "results": map[string]any{"squat_kg": 200.0}}, 1},
		{"list op complete inferred", "health_list_competitions", map[string]any{"master_id": "m", "results": map[string]any{"squat_kg": 200.0}}, 1},
		{"list op list explicit", "health_list_competitions", map[string]any{"op": "list"}, 0},
		{"list op list default", "health_list_competitions", map[string]any{}, 0},
		{"list op failed update", "health_list_competitions", map[string]any{"op": "update", "master_id": "missing", "patch": map[string]any{"notes": "x"}}, 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			memory := store.NewMemory()
			memory.Load("entries", []store.Item{{"pk": athlete, "sk": "COMP#m", "user_status": "available", "start_date": "2027-05-01", "name": "Meet", "units": "kg"}})
			svc := build(t, memory, memory)
			_, _ = call(svc, tc.operation, tc.arguments)
			if got := memory.Bumps[store.AnalysisVersionPK+athlete]; got != tc.bumps {
				t.Fatalf("bumps %d, want %d", got, tc.bumps)
			}
		})
	}
}
