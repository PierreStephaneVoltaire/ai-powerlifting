package store

import (
	"context"
	"testing"

	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type contextClient struct{ requested []string }

func item(value map[string]any) map[string]types.AttributeValue {
	result, _ := attributevalue.MarshalMap(value)
	return result
}

func (c *contextClient) GetItem(_ context.Context, input *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	sk := input.Key["sk"].(*types.AttributeValueMemberS).Value
	if sk == "program#current" {
		return &dynamodb.GetItemOutput{Item: item(map[string]any{"ref_sk": "program#v001"})}, nil
	}
	return &dynamodb.GetItemOutput{Item: item(map[string]any{"current_maxes": map[string]any{"squat": 200}, "lift_profiles": []any{}})}, nil
}
func (c *contextClient) Query(_ context.Context, input *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	partition := input.ExpressionAttributeValues[":pk"].(*types.AttributeValueMemberS).Value
	c.requested = append(c.requested, partition)
	if *input.TableName == "sessions" {
		return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{item(map[string]any{"pk": "athlete", "sk": "session#program#v001#2026-11-01#id", "session_id": "id", "date": "2026-11-01"})}}, nil
	}
	if partition == "CATALOG" {
		return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{item(map[string]any{"sk": "EXERCISE#one", "name": "Squat"}), item(map[string]any{"sk": "EXERCISE#hidden", "name": "Bench"})}}, nil
	}
	return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{item(map[string]any{"sk": "EXERCISE#one", "name": "My Squat"}), item(map[string]any{"sk": "EXERCISE#hidden", "hidden": true})}}, nil
}
func (c *contextClient) TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	return &dynamodb.TransactWriteItemsOutput{}, nil
}

func TestContextUsesAthleteOverlayAndFiltersHiddenExercises(t *testing.T) {
	client := &contextClient{}
	repo := Repository{Client: client, HealthTable: "health", GlossaryTable: "glossary", SessionsTable: "sessions"}
	program, err := repo.ProgramContext(context.Background(), "athlete")
	if err != nil || program["current_maxes"].(map[string]any)["squat"] != float64(200) {
		t.Fatalf("program: %#v, %v", program, err)
	}
	exercises, err := repo.Glossary(context.Background(), "athlete")
	if err != nil || len(exercises) != 1 || exercises[0]["name"] != "My Squat" || len(client.requested) != 2 || client.requested[1] != "ATHLETE#athlete" {
		t.Fatalf("exercises: %#v, %v", exercises, err)
	}
	full, err := repo.Program(context.Background(), "athlete", "")
	if err != nil {
		t.Fatal(err)
	}
	sessions := full["sessions"].([]any)
	if len(sessions) != 1 || sessions[0].(map[string]any)["id"] != "id" || sessions[0].(map[string]any)["pk"] != nil {
		t.Fatalf("sessions: %#v", sessions)
	}
}
