package athlete

import (
	"context"
	"testing"

	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type tables struct {
	health   map[string]map[string]any
	sessions []map[string]any
}

func (f tables) GetItem(_ context.Context, input *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	sk := input.Key["sk"].(*types.AttributeValueMemberS).Value
	item, found := f.health[sk]
	if !found {
		return &dynamodb.GetItemOutput{}, nil
	}
	raw, err := attributevalue.MarshalMap(item)
	return &dynamodb.GetItemOutput{Item: raw}, err
}

func (f tables) Query(_ context.Context, input *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	var items []map[string]types.AttributeValue
	for _, session := range f.sessions {
		raw, _ := attributevalue.MarshalMap(session)
		items = append(items, raw)
	}
	return &dynamodb.QueryOutput{Items: items}, nil
}

func TestProgramFollowsPointerAndMissingProgramIsEmpty(t *testing.T) {
	reader := Dynamo{API: tables{health: map[string]map[string]any{
		"program#current": {"ref_sk": "program#v002"},
		"program#v002":    {"meta": map[string]any{"height_cm": 180}, "lift_profiles": []any{map[string]any{"lift": "squat"}}, "current_maxes": map[string]any{"squat": 200}},
	}}}
	program, err := reader.Program(context.Background(), "a1")
	if err != nil || program.SK != "program#v002" || program.Meta["height_cm"] != 180.0 || len(program.LiftProfiles) != 1 || program.CurrentMaxes["squat"] != 200.0 {
		t.Fatalf("program %+v err %v", program, err)
	}
	empty, err := (Dynamo{API: tables{}}).Program(context.Background(), "a1")
	if err != nil || empty.SK != "" || len(empty.LiftProfiles) != 0 {
		t.Fatalf("empty %+v err %v", empty, err)
	}
}

func TestInstancesKeepOnlyCompletedSessionsOfTheExercise(t *testing.T) {
	reader := Dynamo{API: tables{sessions: []map[string]any{
		{"date": "2026-01-01", "completed": true, "exercises": []any{map[string]any{"name": "Bench Press", "sets": 3, "reps": 5, "kg": 100, "rpe_target": 8}, map[string]any{"name": "Row"}}},
		{"date": "2026-01-02", "status": "planned", "exercises": []any{map[string]any{"name": "Bench Press"}}},
		{"date": "2026-01-03", "status": "logged", "exercises": []any{map[string]any{"name": " bench  press ", "kg": 105, "rpe": 9, "notes": "grindy"}}},
	}}}
	got, err := reader.Instances(context.Background(), "a1", Program{SK: "program#v002"}, "Bench Press")
	if err != nil || len(got) != 2 {
		t.Fatalf("instances %v err %v", got, err)
	}
	if got[0]["rpe"] != 8.0 || got[1]["rpe"] != 9.0 || got[1]["notes"] != "grindy" {
		t.Fatalf("instances %v", got)
	}
	if none, _ := reader.Instances(context.Background(), "a1", Program{}, "Bench Press"); none != nil {
		t.Fatal("instances without a program")
	}
}
