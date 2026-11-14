package store

import (
	"context"
	"sort"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type recorder struct {
	update      *dynamodb.UpdateItemInput
	transaction *dynamodb.TransactWriteItemsInput
	query       *dynamodb.QueryInput
	cancel      bool
}

func (r *recorder) GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	return &dynamodb.GetItemOutput{}, nil
}

func (r *recorder) Query(_ context.Context, input *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	r.query = input
	return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{{"pk": &types.AttributeValueMemberS{Value: "CATALOG"}, "id": &types.AttributeValueMemberS{Value: "a"}}}}, nil
}

func (r *recorder) UpdateItem(_ context.Context, input *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	r.update = input
	return &dynamodb.UpdateItemOutput{}, nil
}

func (r *recorder) TransactWriteItems(_ context.Context, input *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	r.transaction = input
	if r.cancel {
		return nil, &types.TransactionCanceledException{}
	}
	return &dynamodb.TransactWriteItemsOutput{}, nil
}

func TestDynamoUpdateBuildsSetAndRemove(t *testing.T) {
	api := &recorder{}
	d := Dynamo{API: api, Table: "glossary"}
	err := d.Update(context.Background(), OverlayKey("a", "x"), Patch{Set: Item{"archived": true, "name": "Bench"}, Remove: []string{"hidden"}})
	if err != nil {
		t.Fatal(err)
	}
	input := api.update
	expression := *input.UpdateExpression
	if !strings.HasPrefix(expression, "SET ") || !strings.Contains(expression, " REMOVE #r2") {
		t.Fatalf("expression %q", expression)
	}
	var fields []string
	for _, name := range input.ExpressionAttributeNames {
		fields = append(fields, name)
	}
	sort.Strings(fields)
	if strings.Join(fields, ",") != "archived,hidden,name" || len(input.ExpressionAttributeValues) != 2 {
		t.Fatalf("names %v values %v", fields, input.ExpressionAttributeValues)
	}
	if input.Key["pk"].(*types.AttributeValueMemberS).Value != "ATHLETE#a" || *input.TableName != "glossary" {
		t.Fatalf("key %v", input.Key)
	}
}

func TestDynamoCreateCatalogWritesNameLookupAndReportsConflict(t *testing.T) {
	api := &recorder{}
	d := Dynamo{API: api, Table: "glossary"}
	item := Item{"id": "a", "name_key": "bench", "generic_pending": PendingMarker}
	created, err := d.CreateCatalog(context.Background(), item)
	if err != nil || !created {
		t.Fatalf("created %v err %v", created, err)
	}
	puts := api.transaction.TransactItems
	if len(puts) != 2 || puts[1].Put.Item["pk"].(*types.AttributeValueMemberS).Value != "CATALOG_NAME" || *puts[0].Put.ConditionExpression != "attribute_not_exists(pk)" {
		t.Fatalf("transaction %+v", puts)
	}
	api.cancel = true
	if created, err := d.CreateCatalog(context.Background(), item); created || err != nil {
		t.Fatalf("conflict created=%v err=%v", created, err)
	}
}

func TestDynamoPendingQueriesSparseIndex(t *testing.T) {
	api := &recorder{}
	items, err := (Dynamo{API: api, Table: "glossary"}).Pending(context.Background(), 5)
	if err != nil || len(items) != 1 || items[0]["id"] != "a" {
		t.Fatalf("items %v err %v", items, err)
	}
	if *api.query.IndexName != "generic-pending" || *api.query.Limit != 5 {
		t.Fatalf("query %+v", api.query)
	}
}
