package entries

import (
	"context"
	"errors"
	"testing"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/store"
)

func TestFormatTimestampOmitsZeroMicroseconds(t *testing.T) {
	moment := time.Date(2026, 11, 14, 12, 0, 0, 0, time.UTC)
	if got := FormatTimestamp(moment); got != "2026-11-14T12:00:00+00:00" {
		t.Fatal(got)
	}
	if got := FormatTimestamp(moment.Add(123456 * time.Microsecond)); got != "2026-11-14T12:00:00.123456+00:00" {
		t.Fatal(got)
	}
	zone := time.FixedZone("x", -5*3600)
	if got := FormatTimestamp(time.Date(2026, 11, 14, 7, 0, 0, 0, zone)); got != "2026-11-14T12:00:00+00:00" {
		t.Fatal(got)
	}
}

func memoryWith(health ...store.Item) *store.Memory {
	memory := store.NewMemory()
	memory.Load("health", health)
	return memory
}

func TestActiveBlockResolution(t *testing.T) {
	cases := []struct {
		name   string
		health []store.Item
		want   string
	}{
		{"pointer carries the block", []store.Item{{"pk": "a", "sk": "program#current", "current_block_id": "b-pointer", "ref_sk": "program#v1"}}, "b-pointer"},
		{"pointer block of current falls through to the program", []store.Item{
			{"pk": "a", "sk": "program#current", "current_block_id": "current", "ref_sk": "program#v1"},
			{"pk": "a", "sk": "program#v1", "meta": map[string]any{"current_block_id": "b-meta"}},
		}, "b-meta"},
		{"latest active block wins", []store.Item{
			{"pk": "a", "sk": "program#current", "ref_sk": "program#v1"},
			{"pk": "a", "sk": "program#v1", "meta": map[string]any{"blocks": []any{
				map[string]any{"id": "old", "status": "active", "start_date": "2026-01-01"},
				map[string]any{"block_id": "new", "status": "active", "start_date": "2027-01-01"},
				map[string]any{"id": "done", "status": "completed", "start_date": "2028-01-01"},
				"junk",
				map[string]any{"status": "active"},
			}}},
		}, "new"},
		{"configured current with no active block stays current", []store.Item{
			{"pk": "a", "sk": "program#current", "ref_sk": "program#v1"},
			{"pk": "a", "sk": "program#v1", "meta": map[string]any{"current_block_id": "current"}},
		}, "current"},
		{"pointer without ref acts as the program", []store.Item{{"pk": "a", "sk": "program#current", "meta": map[string]any{"current_block_id": "solo"}}}, "solo"},
		{"no pointer at all", nil, "current"},
		{"dangling ref", []store.Item{{"pk": "a", "sk": "program#current", "ref_sk": "program#gone"}}, "current"},
		{"ties on start date break on id", []store.Item{
			{"pk": "a", "sk": "program#current", "ref_sk": "program#v1"},
			{"pk": "a", "sk": "program#v1", "meta": map[string]any{"blocks": []any{
				map[string]any{"id": "b", "status": "active", "start_date": "2027-01-01"},
				map[string]any{"id": "a", "status": "active", "start_date": "2027-01-01"},
			}}},
		}, "b"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := ActiveBlockID(context.Background(), memoryWith(tc.health...), "a")
			if err != nil || got != tc.want {
				t.Fatalf("got %q err %v, want %q", got, err, tc.want)
			}
		})
	}
}

func TestBlockMembership(t *testing.T) {
	cases := []struct {
		record map[string]any
		block  string
		active string
		want   bool
	}{
		{map[string]any{"block_id": "b2"}, "b2", "b2", true},
		{map[string]any{"block": "current"}, "b2", "b2", true},
		{map[string]any{"block_id": "b1"}, "b2", "b2", false},
		{map[string]any{}, "b2", "b2", false},
		{map[string]any{"block_id": "b2"}, "current", "b2", true},
		{map[string]any{"block_id": "b1"}, "b1", "b2", true},
		{map[string]any{"block_id": "b2"}, "b1", "b2", false},
	}
	for index, tc := range cases {
		if got := inBlock(tc.record, tc.block, tc.active); got != tc.want {
			t.Errorf("case %d: got %v want %v", index, got, tc.want)
		}
	}
}

func TestCountryCodes(t *testing.T) {
	cases := map[any]string{"CANADA": "ca", " usa ": "us", "United Kingdom": "gb", "xx": "xx", "": "", nil: "", "Narnia": "narnia"}
	for input, want := range cases {
		if got := countryCode(input); got != want {
			t.Errorf("%v: got %q want %q", input, got, want)
		}
	}
}

type failingEntries struct{ store.Entries }

func (failingEntries) Query(context.Context, string, string) ([]store.Item, error) {
	return nil, errors.New("throttled")
}

func TestListSurfacesStoreFailures(t *testing.T) {
	service := Service{Entries: failingEntries{store.NewMemory()}, Programs: store.NewMemory(), Now: time.Now}
	if _, err := service.List(context.Background(), "a", map[string]any{}); err == nil {
		t.Fatal("store failure swallowed")
	}
}

func TestUpdateValidation(t *testing.T) {
	memory := store.NewMemory()
	memory.Load("entries", []store.Item{{"pk": "a", "sk": "COMP#m", "user_status": "confirmed", "start_date": "2027-01-01", "block_id": "b"}})
	service := Service{Entries: memory, Programs: memory, Now: time.Now}
	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"missing id", map[string]any{"patch": map[string]any{}}, "master_id is required"},
		{"patch not an object", map[string]any{"master_id": "m", "patch": "x"}, "patch must be an object"},
		{"unknown fields are sorted", map[string]any{"master_id": "m", "patch": map[string]any{"z": 1, "a": 2}}, "competition fields are not editable: a, z"},
		{"bad units", map[string]any{"master_id": "m", "patch": map[string]any{"units": "st"}}, "competition.units must be kg or lb"},
		{"not found", map[string]any{"master_id": "nope", "patch": map[string]any{}}, "Competition not found: nope"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := service.Update(context.Background(), "a", tc.args)
			var failure *apperr.Error
			if !errors.As(err, &failure) || failure.Status != 422 || failure.Message != tc.want {
				t.Fatalf("got %v, want 422 %q", err, tc.want)
			}
		})
	}
	if _, err := service.Complete(context.Background(), "a", map[string]any{}); err == nil {
		t.Fatal("complete without master_id accepted")
	}
}

func TestUpdateFailureIsNotReportedAsSuccess(t *testing.T) {
	memory := store.NewMemory()
	memory.Load("entries", []store.Item{{"pk": "a", "sk": "COMP#m", "user_status": "available"}})
	memory.FailUpdate = errors.New("conditional check failed")
	service := Service{Entries: memory, Programs: memory, Now: time.Now}
	if _, err := service.Update(context.Background(), "a", map[string]any{"master_id": "m", "patch": map[string]any{"notes": "x"}}); err == nil {
		t.Fatal("write failure swallowed")
	}
}

func TestReportKeepsAttemptOrderAndIdentity(t *testing.T) {
	existing := map[string]any{"attempts": []any{
		map[string]any{"lift": "bench", "attempt_number": 2.0, "kg": 90.0},
		map[string]any{"lift": "squat", "attempt_number": 1.0, "kg": 100.0, "attempt_id": "kept"},
	}, "grade": 3.0}
	incoming := map[string]any{"attempts": []any{map[string]any{"lift": "squat", "attempt_number": 1.0, "kg": 105.0}}}
	report, err := normaliseReport("m", incoming, existing)
	if err != nil {
		t.Fatal(err)
	}
	attempts := report["attempts"].([]any)
	if len(attempts) != 2 || attempts[0].(map[string]any)["attempt_id"] != "m:bench:2.0" || attempts[1].(map[string]any)["attempt_id"] != "kept" || attempts[1].(map[string]any)["kg"] != 105.0 {
		t.Fatalf("%v", attempts)
	}
	if report["grade"] != 3.0 {
		t.Fatalf("stored report fields lost: %v", report)
	}
}
