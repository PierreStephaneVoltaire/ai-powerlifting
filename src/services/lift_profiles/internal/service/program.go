package service

import (
	"context"
	"errors"
	"sort"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/liftprofiles/internal/apperr"
	"powerlifting/liftprofiles/internal/execution"
	"powerlifting/liftprofiles/internal/profile"
)

type ProgramDB interface {
	GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	UpdateItem(context.Context, *dynamodb.UpdateItemInput, ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
}

type programTransaction interface {
	TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}

type Programs struct {
	DB          ProgramDB
	Table       string
	Definitions profile.Definitions
	Now         func() time.Time
	Bump        func(context.Context, string)
}

func (p Programs) Context(ctx context.Context, athlete string) map[string]any {
	sk, err := p.current(ctx, athlete)
	if err != nil {
		return nil
	}
	output, err := p.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(p.Table), Key: programKey(athlete, sk), ConsistentRead: aws.Bool(true)})
	if err != nil || len(output.Item) == 0 {
		return nil
	}
	var result map[string]any
	if attributevalue.UnmarshalMap(output.Item, &result) != nil || result["published"] == false {
		return nil
	}
	return result
}

func programKey(athlete, sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: athlete}, "sk": &types.AttributeValueMemberS{Value: sk}}
}

func (p Programs) current(ctx context.Context, athlete string) (string, error) {
	output, err := p.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(p.Table), Key: programKey(athlete, "program#current"), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return "", err
	}
	if item, ok := output.Item["ref_sk"].(*types.AttributeValueMemberS); ok && item.Value != "" {
		program, err := p.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(p.Table), Key: programKey(athlete, item.Value), ConsistentRead: aws.Bool(true)})
		if err != nil {
			return "", err
		}
		if len(program.Item) > 0 {
			published, _ := program.Item["published"].(*types.AttributeValueMemberBOOL)
			if published == nil || published.Value {
				return item.Value, nil
			}
		}
	}
	keys := []string{}
	var cursor map[string]types.AttributeValue
	for {
		page, err := p.DB.Query(ctx, &dynamodb.QueryInput{TableName: aws.String(p.Table), KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :prefix)"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: athlete}, ":prefix": &types.AttributeValueMemberS{Value: "program#v"}}, ExclusiveStartKey: cursor, ConsistentRead: aws.Bool(true)})
		if err != nil {
			return "", err
		}
		for _, raw := range page.Items {
			var item map[string]any
			if err := attributevalue.UnmarshalMap(raw, &item); err != nil {
				return "", err
			}
			sk, _ := item["sk"].(string)
			meta, _ := item["meta"].(map[string]any)
			if sk != "program#current" && sk != "" && item["published"] != false && meta["archived"] != true {
				keys = append(keys, sk)
			}
		}
		cursor = page.LastEvaluatedKey
		if len(cursor) == 0 {
			break
		}
	}
	if len(keys) == 0 {
		return "", apperr.NotFound("Program not found")
	}
	sort.Strings(keys)
	return keys[len(keys)-1], nil
}

func (p Programs) Update(ctx context.Context, args map[string]any, _ execution.Inferer) (any, error) {
	athlete, _ := args["pk"].(string)
	sk, _ := args["program_sk"].(string)
	current := sk == "" || sk == "current" || sk == "program#current"
	if current {
		var err error
		sk, err = p.current(ctx, athlete)
		if err != nil {
			return nil, err
		}
	}
	loaded, err := p.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(p.Table), Key: programKey(athlete, sk), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return nil, err
	}
	if len(loaded.Item) == 0 {
		return nil, apperr.NotFound("Program not found: %s", sk)
	}
	var stored map[string]any
	if err := attributevalue.UnmarshalMap(loaded.Item, &stored); err != nil {
		return nil, err
	}
	if stored["published"] == false {
		return nil, apperr.NotFound("Program not found: %s", sk)
	}
	existing, _ := stored["lift_profiles"].([]any)
	requested, _ := args["lift_profiles"].([]any)
	profiles := p.Definitions.Normalize(requested, existing)
	encoded, err := attributevalue.Marshal(profiles)
	if err != nil {
		return nil, err
	}
	now := time.Now
	if p.Now != nil {
		now = p.Now
	}
	stamp := now().UTC().Format(time.RFC3339Nano)
	names := map[string]string{"#profiles": "lift_profiles", "#meta": "meta", "#updated": "updated_at", "#published": "published"}
	values := map[string]types.AttributeValue{":profiles": encoded, ":updated": &types.AttributeValueMemberS{Value: stamp}, ":false": &types.AttributeValueMemberBOOL{Value: false}}
	condition := "attribute_exists(pk) AND (attribute_not_exists(#published) OR #published <> :false)"
	if old, present := loaded.Item["lift_profiles"]; present {
		condition += " AND #profiles = :old"
		values[":old"] = old
	} else {
		condition += " AND attribute_not_exists(#profiles)"
	}
	update := "SET #profiles = :profiles, #meta.#updated = :updated"
	if _, ok := stored["meta"].(map[string]any); !ok {
		update = "SET #profiles = :profiles, #meta = :meta"
		values[":meta"] = &types.AttributeValueMemberM{Value: map[string]types.AttributeValue{"updated_at": &types.AttributeValueMemberS{Value: stamp}}}
		delete(names, "#updated")
		delete(values, ":updated")
		if old, present := loaded.Item["meta"]; present {
			condition += " AND #meta = :old_meta"
			values[":old_meta"] = old
		} else {
			condition += " AND attribute_not_exists(#meta)"
		}
	}
	if current {
		writer, ok := p.DB.(programTransaction)
		if !ok {
			return nil, apperr.Uncertain("Program update unavailable")
		}
		_, err = writer.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{TransactItems: []types.TransactWriteItem{
			{ConditionCheck: &types.ConditionCheck{TableName: aws.String(p.Table), Key: programKey(athlete, "program#current"), ConditionExpression: aws.String("attribute_not_exists(ref_sk) OR ref_sk = :selected"), ExpressionAttributeValues: map[string]types.AttributeValue{":selected": &types.AttributeValueMemberS{Value: sk}}}},
			{Update: &types.Update{TableName: aws.String(p.Table), Key: programKey(athlete, sk), UpdateExpression: aws.String(update), ConditionExpression: aws.String(condition), ExpressionAttributeNames: names, ExpressionAttributeValues: values}},
		}})
	} else {
		_, err = p.DB.UpdateItem(ctx, &dynamodb.UpdateItemInput{TableName: aws.String(p.Table), Key: programKey(athlete, sk), UpdateExpression: aws.String(update), ConditionExpression: aws.String(condition), ExpressionAttributeNames: names, ExpressionAttributeValues: values})
	}
	var conflict *types.ConditionalCheckFailedException
	var canceled *types.TransactionCanceledException
	if errors.As(err, &conflict) || errors.As(err, &canceled) && len(canceled.CancellationReasons) > 0 && (aws.ToString(canceled.CancellationReasons[0].Code) == "ConditionalCheckFailed" || len(canceled.CancellationReasons) > 1 && aws.ToString(canceled.CancellationReasons[1].Code) == "ConditionalCheckFailed") {
		return nil, apperr.Conflict("Program changed; retry the update")
	}
	if err != nil {
		return nil, err
	}
	if p.Bump != nil {
		p.Bump(ctx, athlete)
	}
	return map[string]any{"success": true, "lift_profiles": profiles, "sk": sk, "updated_at": stamp}, nil
}
