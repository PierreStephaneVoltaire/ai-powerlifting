package store

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/redis/go-redis/v9"

	"powerlifting/sessions/internal/value"
)

type stubAPI struct {
	queries     []*dynamodb.QueryInput
	pages       []*dynamodb.QueryOutput
	gets        []*dynamodb.GetItemInput
	getOutput   *dynamodb.GetItemOutput
	puts        []*dynamodb.PutItemInput
	deletes     []*dynamodb.DeleteItemInput
	batches     []*dynamodb.BatchWriteItemInput
	unprocessed int
	failBatch   bool
}

func (s *stubAPI) Query(_ context.Context, in *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	copied := *in
	s.queries = append(s.queries, &copied)
	page := s.pages[0]
	s.pages = s.pages[1:]
	return page, nil
}

func (s *stubAPI) GetItem(_ context.Context, in *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	s.gets = append(s.gets, in)
	return s.getOutput, nil
}

func (s *stubAPI) PutItem(_ context.Context, in *dynamodb.PutItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error) {
	s.puts = append(s.puts, in)
	return &dynamodb.PutItemOutput{}, nil
}

func (s *stubAPI) DeleteItem(_ context.Context, in *dynamodb.DeleteItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.DeleteItemOutput, error) {
	s.deletes = append(s.deletes, in)
	return &dynamodb.DeleteItemOutput{}, nil
}

func (s *stubAPI) BatchWriteItem(_ context.Context, in *dynamodb.BatchWriteItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.BatchWriteItemOutput, error) {
	if s.failBatch {
		return nil, errors.New("boom")
	}
	s.batches = append(s.batches, in)
	if s.unprocessed > 0 {
		s.unprocessed--
		return &dynamodb.BatchWriteItemOutput{UnprocessedItems: in.RequestItems}, nil
	}
	return &dynamodb.BatchWriteItemOutput{}, nil
}

func newDynamo(api *stubAPI) *Dynamo {
	return &Dynamo{API: api, SessionsTable: "if-sessions", HealthTable: "if-health"}
}

func s(v string) types.AttributeValue { return &types.AttributeValueMemberS{Value: v} }

func TestForProgramPagesWithConsistentPrefixQuery(t *testing.T) {
	api := &stubAPI{pages: []*dynamodb.QueryOutput{
		{Items: []map[string]types.AttributeValue{{"sk": s("a")}}, LastEvaluatedKey: map[string]types.AttributeValue{"sk": s("a")}},
		{Items: []map[string]types.AttributeValue{{"sk": s("b")}}},
	}}
	items, err := newDynamo(api).ForProgram(context.Background(), "athlete", "program#v002")
	if err != nil || len(items) != 2 || len(api.queries) != 2 {
		t.Fatalf("items %v queries %d err %v", items, len(api.queries), err)
	}
	first := api.queries[0]
	if *first.TableName != "if-sessions" || !*first.ConsistentRead || *first.KeyConditionExpression != "pk = :pk AND begins_with(sk, :prefix)" {
		t.Fatalf("query %+v", first)
	}
	if first.ExpressionAttributeValues[":prefix"].(*types.AttributeValueMemberS).Value != "session#program#v002#" {
		t.Fatalf("prefix %v", first.ExpressionAttributeValues)
	}
	if api.queries[1].ExclusiveStartKey == nil {
		t.Fatal("second page lacks start key")
	}
}

func TestListingFiltersByProgramAndProjectsSummaryFields(t *testing.T) {
	api := &stubAPI{pages: []*dynamodb.QueryOutput{{}}}
	if _, err := newDynamo(api).Listing(context.Background(), "athlete", "program#v002"); err != nil {
		t.Fatal(err)
	}
	query := api.queries[0]
	if *query.FilterExpression != "#program = :program" || query.ScanIndexForward == nil || *query.ScanIndexForward {
		t.Fatalf("query %+v", query)
	}
	if !strings.Contains(*query.ProjectionExpression, "#f0") || query.ExpressionAttributeNames["#program"] != "program_sk" {
		t.Fatalf("projection %s names %v", *query.ProjectionExpression, query.ExpressionAttributeNames)
	}
}

func TestPutNeverSendsConditionAndEncodesFloatsAsDecimalText(t *testing.T) {
	api := &stubAPI{}
	err := newDynamo(api).Put(context.Background(), value.Item{"pk": "a", "sk": "b", "kg": json.Number("100.5"), "n": json.Number("2.0")})
	if err != nil || len(api.puts) != 1 || api.puts[0].ConditionExpression != nil {
		t.Fatalf("puts %v err %v", api.puts, err)
	}
	if api.puts[0].Item["n"].(*types.AttributeValueMemberN).Value != "2.0" {
		t.Fatalf("item %v", api.puts[0].Item)
	}
}

func TestApplyChunksBatchesAndRetriesUnprocessed(t *testing.T) {
	api := &stubAPI{unprocessed: 2}
	puts := make([]value.Item, 30)
	for i := range puts {
		puts[i] = value.Item{"pk": "a", "sk": string(value.Int(i))}
	}
	dynamo := newDynamo(api)
	dynamo.Sleep = func(_ time.Duration) {}
	if err := dynamo.Apply(context.Background(), "a", []string{"old"}, puts); err != nil {
		t.Fatal(err)
	}
	total := 0
	for _, batch := range api.batches {
		if len(batch.RequestItems["if-sessions"]) > 25 {
			t.Fatalf("batch of %d", len(batch.RequestItems["if-sessions"]))
		}
	}
	for _, batch := range api.batches[len(api.batches)-1:] {
		total += len(batch.RequestItems["if-sessions"])
	}
	if len(api.batches) != 4 || total != 6 {
		t.Fatalf("batches %d last %d", len(api.batches), total)
	}
	api.failBatch = true
	if err := dynamo.Apply(context.Background(), "a", nil, puts[:1]); err == nil {
		t.Fatal("batch failure swallowed")
	}
}

func TestCurrentSKIsEmptyWithoutPointer(t *testing.T) {
	api := &stubAPI{getOutput: &dynamodb.GetItemOutput{}}
	sk, err := newDynamo(api).CurrentSK(context.Background(), "athlete")
	if err != nil || sk != "" {
		t.Fatalf("sk %s err %v", sk, err)
	}
	api.getOutput = &dynamodb.GetItemOutput{Item: map[string]types.AttributeValue{"ref_sk": s("program#v007")}}
	if sk, _ := newDynamo(api).CurrentSK(context.Background(), "athlete"); sk != "program#v007" {
		t.Fatal(sk)
	}
	if !*api.gets[0].ConsistentRead || api.gets[0].Key["sk"].(*types.AttributeValueMemberS).Value != "program#current" {
		t.Fatalf("get %+v", api.gets[0])
	}
}

func TestProgramReadsPhases(t *testing.T) {
	api := &stubAPI{getOutput: &dynamodb.GetItemOutput{Item: map[string]types.AttributeValue{
		"phases": &types.AttributeValueMemberL{Value: []types.AttributeValue{&types.AttributeValueMemberM{Value: map[string]types.AttributeValue{"name": s("P")}}}},
	}}}
	program, err := newDynamo(api).Program(context.Background(), "athlete", "program#v001")
	if err != nil || !program.Found || len(program.Phases) != 1 {
		t.Fatalf("program %+v err %v", program, err)
	}
	api.getOutput = &dynamodb.GetItemOutput{}
	if program, _ := newDynamo(api).Program(context.Background(), "athlete", "program#v001"); program.Found {
		t.Fatal("missing program reported found")
	}
	api.getOutput = &dynamodb.GetItemOutput{Item: map[string]types.AttributeValue{"phases": &types.AttributeValueMemberNULL{Value: true}}}
	if program, _ := newDynamo(api).Program(context.Background(), "athlete", "program#v001"); !program.Found || program.Phases != nil {
		t.Fatalf("program %+v", program)
	}
}

func TestValkeyBumpIncrementsTheSharedAnalysisVersionKey(t *testing.T) {
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	valkey := Valkey{Client: client}
	valkey.Bump(context.Background(), "athlete_1")
	valkey.Bump(context.Background(), "athlete_1")
	valkey.Bump(context.Background(), "")
	if got, _ := server.Get("pl:analysis-version:athlete_1"); got != "2" {
		t.Fatalf("version %q", got)
	}
	if len(server.Keys()) != 1 {
		t.Fatalf("keys %v", server.Keys())
	}
	server.Close()
	valkey.Bump(context.Background(), "athlete_1")
}
