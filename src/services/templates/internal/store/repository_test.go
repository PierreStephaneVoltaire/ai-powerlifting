package store

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"powerlifting/templates/internal/library"
)

type client struct {
	input *dynamodb.TransactWriteItemsInput
	err   error
}

func (c *client) GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	return &dynamodb.GetItemOutput{}, nil
}
func (c *client) Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	return &dynamodb.QueryOutput{}, nil
}
func (c *client) TransactWriteItems(_ context.Context, in *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	c.input = in
	return &dynamodb.TransactWriteItemsOutput{}, c.err
}
func TestAtomicIndexAndTemplateWrites(t *testing.T) {
	fake := &client{}
	db := Repository{Client: fake, Table: "templates"}
	ctx := context.Background()
	item := map[string]any{"pk": "library", "sk": "template#1"}
	index := map[string]any{"pk": "library", "sk": "template#index", "index_revision": "new"}
	for _, remove := range []bool{false, true} {
		if err := db.Commit(ctx, item, remove, nil, index, "previous"); err != nil {
			t.Fatal(err)
		}
		writes := fake.input.TransactItems
		if len(writes) != 2 || writes[0].Put == nil || aws.ToString(writes[0].Put.ConditionExpression) != "#revision = :revision" {
			t.Fatalf("unexpected index write: %#v", writes)
		}
		if remove && writes[1].Delete == nil || !remove && writes[1].Put == nil {
			t.Fatalf("unexpected item write: %#v", writes[1])
		}
	}
	if err := db.Commit(ctx, item, false, nil, index, ""); err != nil {
		t.Fatal(err)
	}
	if aws.ToString(fake.input.TransactItems[0].Put.ConditionExpression) != "attribute_not_exists(#revision)" {
		t.Fatal("legacy index condition missing")
	}
	fake.err = &types.TransactionCanceledException{CancellationReasons: []types.CancellationReason{{Code: aws.String("ConditionalCheckFailed")}}}
	if err := db.Commit(ctx, item, false, nil, index, "previous"); !errors.Is(err, library.ErrConflict) {
		t.Fatalf("conditional conflict = %v", err)
	}
}

func TestImportWriteBindsClaimAtomically(t *testing.T) {
	fake := &client{}
	db := Repository{Client: fake, Table: "templates", HealthTable: "health"}
	claim := &library.ImportClaim{Athlete: "athlete", ImportID: "import-1", ClaimID: "claim-1"}
	err := db.Commit(context.Background(), map[string]any{"pk": "library", "sk": "template#import-1"}, false, claim, map[string]any{"pk": "library", "sk": "template#index"}, "old")
	if err != nil {
		t.Fatal(err)
	}
	writes := fake.input.TransactItems
	if len(writes) != 3 || aws.ToString(writes[1].Put.ConditionExpression) != "attribute_not_exists(pk)" || writes[2].ConditionCheck == nil {
		t.Fatalf("unexpected writes: %#v", writes)
	}
	check := writes[2].ConditionCheck
	if aws.ToString(check.TableName) != "health" || check.Key["pk"].(*types.AttributeValueMemberS).Value != "athlete" || check.Key["sk"].(*types.AttributeValueMemberS).Value != "import#pending#import-1" || check.ExpressionAttributeValues[":claim"].(*types.AttributeValueMemberS).Value != "claim-1" {
		t.Fatalf("unexpected claim check: %#v", check)
	}
}
