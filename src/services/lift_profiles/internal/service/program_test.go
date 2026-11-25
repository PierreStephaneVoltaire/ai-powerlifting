package service

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/profile"
)

type programFake struct {
	item        map[string]types.AttributeValue
	update      *dynamodb.UpdateItemInput
	transaction *dynamodb.TransactWriteItemsInput
	err         error
}

func (f *programFake) GetItem(_ context.Context, in *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	if in.Key["sk"].(*types.AttributeValueMemberS).Value == "program#current" {
		return &dynamodb.GetItemOutput{Item: map[string]types.AttributeValue{"ref_sk": &types.AttributeValueMemberS{Value: "program#001"}}}, nil
	}
	return &dynamodb.GetItemOutput{Item: f.item}, nil
}
func (f *programFake) Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	return &dynamodb.QueryOutput{}, nil
}
func (f *programFake) UpdateItem(_ context.Context, input *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	f.update = input
	return &dynamodb.UpdateItemOutput{}, nil
}
func (f *programFake) TransactWriteItems(_ context.Context, input *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	f.transaction = input
	return &dynamodb.TransactWriteItemsOutput{}, f.err
}

func TestUpdateRejectsChangedCurrentProgram(t *testing.T) {
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	stored, err := attributevalue.MarshalMap(map[string]any{"pk": "athlete", "sk": "program#001", "meta": map[string]any{}})
	if err != nil {
		t.Fatal(err)
	}
	db := &programFake{item: stored, err: &types.TransactionCanceledException{CancellationReasons: []types.CancellationReason{{Code: aws.String("ConditionalCheckFailed")}}}}
	bumped := false
	p := Programs{DB: db, Table: "health", Definitions: defs, Bump: func(context.Context, string) { bumped = true }}
	_, err = p.Update(context.Background(), map[string]any{"pk": "athlete", "lift_profiles": []any{}}, nil)
	var failure *apperr.Error
	if !errors.As(err, &failure) || failure.Status != 409 || bumped {
		t.Fatalf("got %v, bumped %v", err, bumped)
	}
}

func TestUpdatePreservesStoredVideosAndConditionsOnOriginalProfiles(t *testing.T) {
	defs, err := profile.Defaults()
	if err != nil {
		t.Fatal(err)
	}
	stored, err := attributevalue.MarshalMap(map[string]any{"pk": "athlete", "sk": "program#001", "meta": map[string]any{}, "lift_profiles": []any{map[string]any{"lift": "squat", "form_videos": map[string]any{"front": map[string]any{"id": "original"}}}}})
	if err != nil {
		t.Fatal(err)
	}
	db := &programFake{item: stored}
	bumped := ""
	p := Programs{DB: db, Table: "health", Definitions: defs, Bump: func(_ context.Context, athlete string) { bumped = athlete }}
	result, err := p.Update(context.Background(), map[string]any{"pk": "athlete", "lift_profiles": []any{map[string]any{"lift": "squat", "form_videos": map[string]any{"front": map[string]any{"id": "forged"}}}}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	profiles := result.(map[string]any)["lift_profiles"].([]any)
	videos := profiles[0].(map[string]any)["form_videos"].(map[string]any)
	if db.transaction == nil || len(db.transaction.TransactItems) != 2 {
		t.Fatalf("missing transaction: %#v", db.transaction)
	}
	pointer := db.transaction.TransactItems[0].ConditionCheck
	update := db.transaction.TransactItems[1].Update
	if videos["front"].(map[string]any)["id"] != "original" || bumped != "athlete" || update.ExpressionAttributeValues[":old"] == nil || update.Key["sk"].(*types.AttributeValueMemberS).Value != "program#001" || pointer.ExpressionAttributeValues[":selected"].(*types.AttributeValueMemberS).Value != "program#001" {
		t.Fatalf("unexpected update: %#v %#v", result, db.transaction)
	}
}
