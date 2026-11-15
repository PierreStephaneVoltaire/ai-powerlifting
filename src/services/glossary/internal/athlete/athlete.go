package athlete

import (
	"context"
	"slices"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/glossary/internal/exercise"
)

const (
	pointerSK     = "program#current"
	sessionPrefix = "session#"
	maxInstances  = 20
)

type Program struct {
	SK           string
	Meta         map[string]any
	LiftProfiles []map[string]any
	CurrentMaxes map[string]any
}

type Reader interface {
	Program(ctx context.Context, athlete string) (Program, error)
	Instances(ctx context.Context, athlete string, program Program, name string) ([]map[string]any, error)
}

type API interface {
	GetItem(ctx context.Context, input *dynamodb.GetItemInput, options ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(ctx context.Context, input *dynamodb.QueryInput, options ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
}

type Dynamo struct {
	API           API
	HealthTable   string
	SessionsTable string
}

func (d Dynamo) get(ctx context.Context, athlete, sk string) (map[string]any, error) {
	output, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: &d.HealthTable,
		Key:       map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: athlete}, "sk": &types.AttributeValueMemberS{Value: sk}},
	})
	if err != nil || output.Item == nil {
		return nil, err
	}
	item := map[string]any{}
	return item, attributevalue.UnmarshalMap(output.Item, &item)
}

func objects(value any) []map[string]any {
	list, _ := value.([]any)
	out := make([]map[string]any, 0, len(list))
	for _, entry := range list {
		if object, ok := entry.(map[string]any); ok {
			out = append(out, object)
		}
	}
	return out
}

func (d Dynamo) Program(ctx context.Context, athlete string) (Program, error) {
	pointer, err := d.get(ctx, athlete, pointerSK)
	if err != nil {
		return Program{}, err
	}
	sk, _ := pointer["ref_sk"].(string)
	if sk == "" {
		return Program{}, nil
	}
	item, err := d.get(ctx, athlete, sk)
	if err != nil {
		return Program{}, err
	}
	meta, _ := item["meta"].(map[string]any)
	maxes, _ := item["current_maxes"].(map[string]any)
	return Program{SK: sk, Meta: meta, LiftProfiles: objects(item["lift_profiles"]), CurrentMaxes: maxes}, nil
}

func (d Dynamo) Instances(ctx context.Context, athlete string, program Program, name string) ([]map[string]any, error) {
	if program.SK == "" {
		return nil, nil
	}
	paginator := dynamodb.NewQueryPaginator(d.API, &dynamodb.QueryInput{
		TableName:                 &d.SessionsTable,
		KeyConditionExpression:    aws.String("pk = :pk AND begins_with(sk, :prefix)"),
		ProjectionExpression:      aws.String("#date, completed, #status, exercises"),
		ExpressionAttributeNames:  map[string]string{"#date": "date", "#status": "status"},
		ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: athlete}, ":prefix": &types.AttributeValueMemberS{Value: sessionPrefix + program.SK + "#"}},
	})
	key := exercise.NameKey(name)
	var instances []map[string]any
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, raw := range page.Items {
			session := map[string]any{}
			if err := attributevalue.UnmarshalMap(raw, &session); err != nil {
				return nil, err
			}
			instances = append(instances, performed(session, key)...)
		}
	}
	if len(instances) > maxInstances {
		instances = instances[len(instances)-maxInstances:]
	}
	return instances, nil
}

func performed(session map[string]any, key string) []map[string]any {
	status, _ := session["status"].(string)
	completed, _ := session["completed"].(bool)
	if !completed && !slices.Contains([]string{"logged", "completed"}, status) {
		return nil
	}
	var instances []map[string]any
	for _, entry := range objects(session["exercises"]) {
		name, _ := entry["name"].(string)
		if exercise.NameKey(name) != key {
			continue
		}
		rpe, present := entry["rpe"]
		if !present {
			rpe = entry["rpe_target"]
		}
		instances = append(instances, map[string]any{
			"date": session["date"], "sets": entry["sets"], "reps": entry["reps"], "kg": entry["kg"], "rpe": rpe, "notes": entry["notes"],
		})
	}
	return instances
}
