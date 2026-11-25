package store

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type fakeReader struct {
	queries []*dynamodb.QueryInput
	fail    bool
}

func (f *fakeReader) GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	return &dynamodb.GetItemOutput{}, nil
}

func (f *fakeReader) Query(_ context.Context, in *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	if f.fail {
		return nil, errors.New("unavailable")
	}
	copyInput := *in
	f.queries = append(f.queries, &copyInput)
	if len(in.ExclusiveStartKey) == 0 {
		return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{ToItem(map[string]any{"sk": "first"})}, LastEvaluatedKey: ToItem(map[string]any{"sk": "first"})}, nil
	}
	return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{ToItem(map[string]any{"sk": "second"})}}, nil
}

func TestReaderPaginatesAndRestrictsCompetitionDates(t *testing.T) {
	fake := &fakeReader{}
	reader := Reader{DB: fake, CompetitionTable: "entries"}
	items, err := reader.Competitions(context.Background(), "person", "2026-01-01", "2026-12-31")
	if err != nil || len(items) != 2 || items[1]["sk"] != "second" {
		t.Fatalf("items=%v err=%v", items, err)
	}
	if len(fake.queries) != 2 || aws.ToString(fake.queries[0].KeyConditionExpression) != "pk = :pk AND entry_date BETWEEN :start AND :end" || aws.ToString(fake.queries[0].IndexName) != "entries-by-date" || len(fake.queries[1].ExclusiveStartKey) == 0 {
		t.Fatalf("queries=%+v", fake.queries)
	}
	fake.fail = true
	if _, err := reader.Query(context.Background(), "sessions", "person", "session#"); err == nil {
		t.Fatal("query error was ignored")
	}
}
