package generation

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

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

func TestCompleteShardsAndResult(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	record, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	long := strings.Repeat("x", 170000)
	if err := store.Complete(ctx, "gen", map[string]any{"summary": long, "n": json.Number("2.50")}, record.Attempt); err != nil {
		t.Fatal(err)
	}
	done, _ := store.Get(ctx, "gen")
	if done.Status != StatusDone || done.Shards != 3 {
		t.Fatalf("got %+v", done)
	}
	for index := 0; index < 3; index++ {
		shard, _ := store.Backend.Get(ctx, "analysis#athlete_1", "native_generation#gen#result#1#"+string(rune('0'+index)))
		if shard == nil || shard["expires_at"] == nil || len(shard["payload"].(string)) > 80000 {
			t.Fatalf("shard %d: %v", index, shard)
		}
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
	if expires := store.Backendexpiry(t, "gen"); expires != 1_800_000_000+180*24*3600 {
		t.Fatalf("expires_at %d", expires)
	}
}

func (s Store) Backendexpiry(t *testing.T, id string) int64 {
	t.Helper()
	item, _ := s.Backend.Get(context.Background(), s.pk(), s.sk(id))
	return int64(toInt(item["expires_at"]))
}

func TestResultIncomplete(t *testing.T) {
	ctx := context.Background()
	store, _ := newStore()
	record, _, _ := store.Reserve(ctx, "gen", "op", "person", false, nil)
	record.Shards = 2
	if _, err := store.Result(ctx, record); !errors.Is(err, ErrIncomplete) {
		t.Fatalf("got %v", err)
	}
}

type fakeAPI struct {
	puts    []*dynamodb.PutItemInput
	updates []*dynamodb.UpdateItemInput
	failPut bool
}

func (f *fakeAPI) GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	return &dynamodb.GetItemOutput{}, nil
}

func (f *fakeAPI) PutItem(_ context.Context, input *dynamodb.PutItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error) {
	f.puts = append(f.puts, input)
	if f.failPut {
		return nil, &types.ConditionalCheckFailedException{}
	}
	return &dynamodb.PutItemOutput{}, nil
}

func (f *fakeAPI) UpdateItem(_ context.Context, input *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	f.updates = append(f.updates, input)
	return &dynamodb.UpdateItemOutput{}, &types.ConditionalCheckFailedException{}
}

func TestDynamoConditions(t *testing.T) {
	api := &fakeAPI{}
	backend := Dynamo{API: api, Table: "if-powerlifting-analysis-cache"}
	ctx := context.Background()
	item := Item{"pk": "analysis#a", "sk": "native_generation#g", "attempt": 2, "access_requirements": nil}
	if created, err := backend.PutIfAbsent(ctx, item); err != nil || !created {
		t.Fatalf("put if absent: %v %v", created, err)
	}
	if *api.puts[0].ConditionExpression != "attribute_not_exists(pk)" {
		t.Fatal("wrong absent condition")
	}
	if _, isNull := api.puts[0].Item["access_requirements"].(*types.AttributeValueMemberNULL); !isNull {
		t.Fatal("nil requirements must be stored as NULL")
	}
	api.failPut = true
	if created, err := backend.PutIfCurrent(ctx, item, "failed", 1); err != nil || created {
		t.Fatalf("lost race must be reported, not raised: %v %v", created, err)
	}
	if *api.puts[1].ConditionExpression != "#status=:previous AND attempt=:attempt" {
		t.Fatal("wrong current condition")
	}
	if err := backend.Update(ctx, "analysis#a", "native_generation#g", 2, Item{"status": "succeeded", "shards": 1}); err != nil {
		t.Fatalf("stale attempt must be ignored: %v", err)
	}
	update := api.updates[0]
	if *update.UpdateExpression != "SET #f0=:v0, #f1=:v1" || *update.ConditionExpression != "#attempt=:attempt" {
		t.Fatalf("unexpected update %s / %s", *update.UpdateExpression, *update.ConditionExpression)
	}
}
