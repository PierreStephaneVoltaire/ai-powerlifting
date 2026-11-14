package generation

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"powerlifting/analytics-ai/internal/pyjson"
)

type vectors struct {
	Fingerprints []struct {
		Operation string `json:"operation"`
		Inputs    string `json:"inputs"`
		Identity  string `json:"identity"`
		ID        string `json:"id"`
	} `json:"fingerprints"`
}

func decodeObject(t *testing.T, text string) map[string]any {
	t.Helper()
	value, err := pyjson.Decode([]byte(text))
	if err != nil {
		t.Fatal(err)
	}
	object, _ := value.(map[string]any)
	return object
}

func TestFingerprintMatchesPython(t *testing.T) {
	raw, err := os.ReadFile("testdata/vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var data vectors
	if err := json.Unmarshal(raw, &data); err != nil {
		t.Fatal(err)
	}
	if len(data.Fingerprints) == 0 {
		t.Fatal("no vectors")
	}
	for index, vector := range data.Fingerprints {
		got, err := Fingerprint(vector.Operation, decodeObject(t, vector.Inputs), decodeObject(t, vector.Identity))
		if err != nil {
			t.Fatal(err)
		}
		if got != vector.ID {
			t.Errorf("vector %d (%s): got %s want %s", index, vector.Operation, got, vector.ID)
		}
	}
}

func TestFingerprintHardcodedVector(t *testing.T) {
	arguments := map[string]any{"pk": "a", "weeks": json.Number("4"), "refresh": true, "_x": json.Number("1")}
	identity := map[string]any{
		"access_requirements": map[string]any{"permissions": []any{"analytics:read"}, "competition_ids": []any{}},
		"analysis_version":    "0",
		"date":                "2026-11-12",
	}
	const want = "d895dd502571eeec389abc322539dad84779d565292b2d040c84930dc6a5268c"
	got, _ := Fingerprint("correlation_analysis", arguments, identity)
	if got != want {
		t.Fatalf("got %s want %s", got, want)
	}
	delete(arguments, "refresh")
	arguments["cache_only"] = false
	again, _ := Fingerprint("correlation_analysis", arguments, identity)
	if again != want {
		t.Fatal("refresh, cache_only and underscore fields must not affect identity")
	}
}

func TestReadRequirements(t *testing.T) {
	access := map[string]any{
		"permissions":       []any{"program:write", "sessions:read", "analytics:read", "unknown:read", "profile:read"},
		"competition_scope": map[string]any{"read": []any{"COMP#1"}},
	}
	got := ReadRequirements(access)
	want := `{"competition_ids": ["COMP#1"], "permissions": ["analytics:read", "profile:read", "sessions:read"]}`
	encoded, _ := pyjson.Encode(got)
	if string(encoded) != want {
		t.Fatalf("got %s", encoded)
	}
}

func TestAuthorizeSource(t *testing.T) {
	access := map[string]any{"permissions": []any{"analytics:read", "competition:read"}, "competition_scope": map[string]any{"read": []any{"COMP#1", "2"}}}
	requirements := func(ids ...any) map[string]any {
		return map[string]any{"permissions": []any{"analytics:read", "competition:read"}, "competition_ids": ids}
	}
	cases := []struct {
		name         string
		requirements map[string]any
		access       map[string]any
		want         error
	}{
		{"legacy record regenerates", nil, access, ErrRegenerate},
		{"legacy record for self", nil, map[string]any{"is_self": true}, nil},
		{"subset allowed", requirements("1", "COMP#2"), access, nil},
		{"outside grant", requirements("3"), access, ErrOutsideGrant},
		{"permission revoked", requirements("1"), map[string]any{"permissions": []any{"analytics:read"}}, ErrAccessChanged},
		{"null scope is unrestricted", requirements("9"), map[string]any{"permissions": []any{"analytics:read", "competition:read"}, "competition_scope": map[string]any{"read": nil}}, nil},
		{"missing scope is empty", requirements("1"), map[string]any{"permissions": []any{"analytics:read", "competition:read"}}, ErrOutsideGrant},
	}
	for _, tc := range cases {
		if err := AuthorizeSource(tc.requirements, tc.access); !errors.Is(err, tc.want) {
			t.Errorf("%s: got %v want %v", tc.name, err, tc.want)
		}
	}
}

func newStore() (Store, *time.Time) {
	clock := time.Unix(1_800_000_000, 0)
	return Store{Athlete: "athlete_1", Backend: NewMemory(), Now: func() time.Time { return clock }}, &clock
}

func TestReserveLifecycle(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	first, created, err := store.Reserve(ctx, "gen", "correlation_analysis", "person", false, map[string]any{"permissions": []any{}})
	if err != nil || !created || first.Attempt != 1 || first.Status != "starting" {
		t.Fatalf("first reserve: %+v %v %v", first, created, err)
	}
	again, created, _ := store.Reserve(ctx, "gen", "correlation_analysis", "person", true, nil)
	if created || again.Attempt != 1 {
		t.Fatalf("running generation must not be retried: %+v", again)
	}
	if err := store.Update(ctx, "gen", 1, Item{"status": "failed", "error": "boom"}); err != nil {
		t.Fatal(err)
	}
	plain, created, _ := store.Reserve(ctx, "gen", "correlation_analysis", "person", false, nil)
	if created || plain.Status != "failed" {
		t.Fatalf("failed generation needs explicit retry: %+v", plain)
	}
	retried, created, _ := store.Reserve(ctx, "gen", "correlation_analysis", "person", true, nil)
	if !created || retried.Attempt != 2 {
		t.Fatalf("retry: %+v %v", retried, created)
	}
	if err := store.Update(ctx, "gen", 1, Item{"status": "failed"}); err != nil {
		t.Fatal(err)
	}
	current, _ := store.Get(ctx, "gen")
	if current.Status != "starting" {
		t.Fatal("stale attempt must not update the record")
	}
}

func TestRefreshRegeneratesSucceededReports(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	first, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	if err := store.Complete(ctx, "gen", map[string]any{"summary": "old"}, first.Attempt); err != nil {
		t.Fatal(err)
	}
	if kept, created, _ := store.Reserve(ctx, "gen", "op", "person", false, nil); created || kept.Status != StatusDone {
		t.Fatalf("a succeeded report must be reused without refresh: %+v", kept)
	}
	next, created, _ := store.Reserve(ctx, "gen", "op", "person", true, nil)
	if !created || next.Attempt != 2 {
		t.Fatalf("refresh must start a new attempt: %+v", next)
	}
}

func TestCompleteAndResult(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	record, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	long := strings.Repeat("x", 170000)
	if err := store.Complete(ctx, "gen", map[string]any{"summary": long, "n": json.Number("2.50")}, record.Attempt); err != nil {
		t.Fatal(err)
	}
	done, _ := store.Get(ctx, "gen")
	if done.Status != StatusDone {
		t.Fatalf("got %+v", done)
	}
	result, err := store.Result(ctx, done)
	if err != nil {
		t.Fatal(err)
	}
	object := result.(map[string]any)
	if object["summary"] != long || object["cached"] != true || object["n"].(json.Number).String() != "2.5" {
		t.Fatalf("unexpected result %v", object["n"])
	}
	if done.Requirements != nil {
		t.Fatal("requirements must stay null when none were stored")
	}
}

func TestPointerRestoredFromObject(t *testing.T) {
	ctx := context.Background()
	reports := NewMemory()
	store := Store{Athlete: "athlete_1", Backend: reports, Now: time.Now}
	record, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	if err := store.Complete(ctx, "gen", map[string]any{"summary": "kept"}, record.Attempt); err != nil {
		t.Fatal(err)
	}
	delete(reports.Pointers.(*memoryPointers).items, pointerKey("athlete_1", "gen"))
	restored, err := store.Get(ctx, "gen")
	if err != nil || restored == nil || restored.Status != StatusDone {
		t.Fatalf("missing pointer must be restored from the stored report: %+v %v", restored, err)
	}
	if _, found, _ := reports.Pointers.Get(ctx, pointerKey("athlete_1", "gen")); !found {
		t.Fatal("pointer must be written back")
	}
}

func TestResultIncomplete(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	record, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	if _, err := store.Result(ctx, record); !errors.Is(err, ErrIncomplete) {
		t.Fatalf("got %v", err)
	}
}
