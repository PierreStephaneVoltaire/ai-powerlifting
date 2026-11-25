package store

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/redis/go-redis/v9"
)

type fakeAPI struct {
	gets    []*dynamodb.GetItemInput
	queries []*dynamodb.QueryInput
	updates []*dynamodb.UpdateItemInput
	pages   [][]map[string]types.AttributeValue
	item    map[string]types.AttributeValue
	failure error
}

func (f *fakeAPI) GetItem(_ context.Context, input *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	f.gets = append(f.gets, input)
	return &dynamodb.GetItemOutput{Item: f.item}, f.failure
}

func (f *fakeAPI) Query(_ context.Context, input *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	copied := *input
	f.queries = append(f.queries, &copied)
	if f.failure != nil {
		return nil, f.failure
	}
	page := f.pages[len(f.queries)-1]
	out := &dynamodb.QueryOutput{Items: page}
	if len(f.queries) < len(f.pages) {
		out.LastEvaluatedKey = map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: "next"}}
	}
	return out, nil
}

func (f *fakeAPI) UpdateItem(_ context.Context, input *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	f.updates = append(f.updates, input)
	return &dynamodb.UpdateItemOutput{}, f.failure
}

func tables() Tables {
	return Tables{Entries: "entries", Health: "health", Sessions: "sessions"}
}

func row(sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: "a"}, "sk": &types.AttributeValueMemberS{Value: sk}}
}

func TestEntryReadsAreConsistentAndProgramReadsAreNot(t *testing.T) {
	api := &fakeAPI{item: row("COMP#x")}
	d := Dynamo{API: api, Tables: tables()}
	if item, err := d.Get(context.Background(), "a", "COMP#x"); err != nil || item["sk"] != "COMP#x" {
		t.Fatalf("%v %v", item, err)
	}
	if _, err := d.Pointer(context.Background(), "a"); err != nil {
		t.Fatal(err)
	}
	if _, err := d.Item(context.Background(), "a", "program#v001"); err != nil {
		t.Fatal(err)
	}
	if *api.gets[0].TableName != "entries" || !*api.gets[0].ConsistentRead {
		t.Errorf("entry get %+v", api.gets[0])
	}
	if *api.gets[1].TableName != "health" || *api.gets[1].ConsistentRead || api.gets[1].Key["sk"].(*types.AttributeValueMemberS).Value != "program#current" {
		t.Errorf("pointer get %+v", api.gets[1])
	}
	api.item = nil
	if item, err := d.Get(context.Background(), "a", "COMP#none"); err != nil || item != nil {
		t.Fatalf("missing item must be nil, got %v %v", item, err)
	}
}

func TestQueriesPaginateAndTargetTheRightKeys(t *testing.T) {
	api := &fakeAPI{pages: [][]map[string]types.AttributeValue{{row("COMP#a")}, {row("COMP#b")}}}
	d := Dynamo{API: api, Tables: tables()}
	items, err := d.Query(context.Background(), "a", EntrySKPrefix)
	if err != nil || len(items) != 2 {
		t.Fatalf("%v %v", items, err)
	}
	if *api.queries[0].KeyConditionExpression != "pk = :pk AND begins_with(sk, :prefix)" || api.queries[1].ExclusiveStartKey == nil || api.queries[0].IndexName != nil {
		t.Fatalf("%+v", api.queries)
	}
	api.queries, api.pages = nil, [][]map[string]types.AttributeValue{{row("COMP#c")}}
	if _, err := d.QueryByDate(context.Background(), "a"); err != nil {
		t.Fatal(err)
	}
	if *api.queries[0].IndexName != EntriesByDate || *api.queries[0].KeyConditionExpression != "pk = :pk" {
		t.Fatalf("%+v", api.queries[0])
	}
	api.queries, api.pages = nil, [][]map[string]types.AttributeValue{{}}
	if _, err := d.Sessions(context.Background(), "a", "program#v002"); err != nil {
		t.Fatal(err)
	}
	if *api.queries[0].TableName != "sessions" || api.queries[0].ExpressionAttributeValues[":prefix"].(*types.AttributeValueMemberS).Value != "session#program#v002#" {
		t.Fatalf("%+v", api.queries[0])
	}
	api.failure = errors.New("throttled")
	if _, err := d.Query(context.Background(), "a", ""); err == nil {
		t.Fatal("query failure swallowed")
	}
}

func TestUpdateExpressionMatchesTheLegacyShape(t *testing.T) {
	expression, names, values := UpdateExpression(EntryUpdate{
		UpdatedAt: "2026-11-14T12:00:00+00:00",
		Set:       []Field{{Name: "notes", Value: "hi"}, {Name: "weight_class_kg", Value: json.Number("93.0")}, {Name: "decision_date", Value: nil}},
		Remove:    []string{"entry_date"},
	})
	if want := "SET #updated_at = :updated, #notes = :value_notes, #weight_class_kg = :value_weight_class_kg, #decision_date = :value_decision_date REMOVE #entry_date"; expression != want {
		t.Fatalf("got %q want %q", expression, want)
	}
	if names["#notes"] != "notes" || names["#entry_date"] != "entry_date" || names["#updated_at"] != "updated_at" || len(names) != 5 {
		t.Fatalf("%v", names)
	}
	if number := values[":value_weight_class_kg"].(*types.AttributeValueMemberN).Value; number != "93" {
		t.Fatalf("number %q", number)
	}
	if _, isNull := values[":value_decision_date"].(*types.AttributeValueMemberNULL); !isNull {
		t.Fatal("null patch must write a NULL attribute")
	}
	bare, _, _ := UpdateExpression(EntryUpdate{UpdatedAt: "t"})
	if strings.Contains(bare, "REMOVE") {
		t.Fatalf("%q", bare)
	}
}

func TestProjectionUpdateWritesNullsAndNumbers(t *testing.T) {
	api := &fakeAPI{}
	d := Dynamo{API: api, Tables: tables()}
	err := d.SaveProjection(context.Background(), "a", "COMP#x", Projection{
		Values:       []Field{{Name: "squat_kg", Value: 200.5}, {Name: "bench_kg", Value: nil}, {Name: "total_kg", Value: 565.0}},
		SnapshotDate: "2027-04-24", UpdatedAt: "now",
	})
	if err != nil {
		t.Fatal(err)
	}
	call := api.updates[0]
	if *call.UpdateExpression != "SET projected_at_t_minus_1w = :projection, projection_snapshot_date = :snapshot, updated_at = :now" {
		t.Fatal(*call.UpdateExpression)
	}
	fields := call.ExpressionAttributeValues[":projection"].(*types.AttributeValueMemberM).Value
	if fields["squat_kg"].(*types.AttributeValueMemberN).Value != "200.5" || fields["total_kg"].(*types.AttributeValueMemberN).Value != "565" {
		t.Fatalf("%v", fields)
	}
	if _, isNull := fields["bench_kg"].(*types.AttributeValueMemberNULL); !isNull {
		t.Fatal("missing lift must be NULL")
	}
	if call.ExpressionAttributeNames != nil {
		t.Fatal("legacy projection update uses no name placeholders")
	}
}

func TestAttributeRoundTrip(t *testing.T) {
	original := map[string]any{
		"s": "x", "n": json.Number("12"), "f": 1.5, "i": 3, "b": true, "z": nil,
		"l": []any{json.Number("1"), "two"}, "m": map[string]any{"k": json.Number("2.50")},
	}
	back := FromItem(ToItem(original))
	if back["n"] != 12.0 || back["f"] != 1.5 || back["i"] != 3.0 || back["b"] != true || back["z"] != nil || back["s"] != "x" {
		t.Fatalf("%v", back)
	}
	if back["m"].(map[string]any)["k"] != 2.5 || back["l"].([]any)[0] != 1.0 {
		t.Fatalf("%v", back)
	}
	if text := numberText("1e2"); text != "100" {
		t.Fatalf("exponent literal %q", text)
	}
	sets := FromAttr(&types.AttributeValueMemberSS{Value: []string{"b", "a"}}).([]any)
	numbers := FromAttr(&types.AttributeValueMemberNS{Value: []string{"1", "2.5"}}).([]any)
	if sets[0] != "a" || numbers[1] != 2.5 {
		t.Fatalf("%v %v", sets, numbers)
	}
}

func TestValkeyBumpUsesTheLegacyKey(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	versions := Valkey{Client: client}
	for range 2 {
		if err := versions.Bump(context.Background(), "athlete-1"); err != nil {
			t.Fatal(err)
		}
	}
	value, err := server.Get("pl:analysis-version:athlete-1")
	if err != nil || value != "2" {
		t.Fatalf("%q %v", value, err)
	}
	server.Close()
	if err := versions.Bump(context.Background(), "athlete-1"); err == nil {
		t.Fatal("outage must surface so the caller can log it")
	}
}

func TestMemoryStoreBehavesLikeTheTables(t *testing.T) {
	memory := NewMemory()
	memory.Load("entries", []Item{
		{"pk": "a", "sk": "COMP#b", "entry_date": "2027-02-01"},
		{"pk": "a", "sk": "COMP#a", "entry_date": "2027-03-01"},
		{"pk": "a", "sk": "COMP#c"},
		{"pk": "b", "sk": "COMP#z", "entry_date": "2027-01-01"},
	})
	listed, _ := memory.Query(context.Background(), "a", EntrySKPrefix)
	if len(listed) != 3 || listed[0]["sk"] != "COMP#a" {
		t.Fatalf("%v", listed)
	}
	indexed, _ := memory.QueryByDate(context.Background(), "a")
	if len(indexed) != 2 || indexed[0]["sk"] != "COMP#b" {
		t.Fatalf("sparse index ordering: %v", indexed)
	}
	if err := memory.Update(context.Background(), "a", "COMP#c", EntryUpdate{UpdatedAt: "t", Set: []Field{{Name: "notes", Value: json.Number("4")}}, Remove: []string{"entry_date"}}); err != nil {
		t.Fatal(err)
	}
	if got, _ := memory.Get(context.Background(), "a", "COMP#c"); got["notes"] != 4.0 || got["updated_at"] != "t" {
		t.Fatalf("%v", got)
	}
}

func TestGlossaryEntriesQueryGlossaryTable(t *testing.T) {
	api := &fakeAPI{pages: [][]map[string]types.AttributeValue{{row("EXERCISE#a")}}}
	d := Dynamo{API: api, Tables: Tables{Glossary: "glossary"}}
	items, err := d.GlossaryEntries(context.Background(), "CATALOG")
	if err != nil || len(items) != 1 {
		t.Fatalf("%v %v", err, items)
	}
	query := api.queries[0]
	if *query.TableName != "glossary" || query.ExpressionAttributeValues[":prefix"].(*types.AttributeValueMemberS).Value != "EXERCISE#" {
		t.Fatalf("%+v", query)
	}
}
