package store

import (
	"context"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type ReadClient interface {
	GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
}

type Reader struct {
	DB               ReadClient
	CompetitionTable string
}

func (r Reader) Get(ctx context.Context, table, pk, sk string) (map[string]any, error) {
	out, err := r.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(table), Key: ToItem(map[string]any{"pk": pk, "sk": sk}), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return nil, err
	}
	if len(out.Item) == 0 {
		return nil, nil
	}
	return FromItem(out.Item), nil
}

func (r Reader) Query(ctx context.Context, table, pk, prefix string) ([]map[string]any, error) {
	input := &dynamodb.QueryInput{TableName: aws.String(table), KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :prefix)"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}, ":prefix": &types.AttributeValueMemberS{Value: prefix}}}
	return r.query(ctx, input)
}

func (r Reader) Competitions(ctx context.Context, pk, start, end string) ([]map[string]any, error) {
	input := &dynamodb.QueryInput{TableName: aws.String(r.CompetitionTable), IndexName: aws.String("entries-by-date"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}}}
	expression := "pk = :pk"
	if start != "" && end != "" {
		expression += " AND entry_date BETWEEN :start AND :end"
		input.ExpressionAttributeValues[":start"] = &types.AttributeValueMemberS{Value: start}
		input.ExpressionAttributeValues[":end"] = &types.AttributeValueMemberS{Value: end}
	} else if start != "" {
		expression += " AND entry_date >= :start"
		input.ExpressionAttributeValues[":start"] = &types.AttributeValueMemberS{Value: start}
	} else if end != "" {
		expression += " AND entry_date <= :end"
		input.ExpressionAttributeValues[":end"] = &types.AttributeValueMemberS{Value: end}
	}
	input.KeyConditionExpression = aws.String(expression)
	return r.query(ctx, input)
}

func (r Reader) query(ctx context.Context, input *dynamodb.QueryInput) ([]map[string]any, error) {
	items := []map[string]any{}
	for {
		page, err := r.DB.Query(ctx, input)
		if err != nil {
			return nil, err
		}
		for _, item := range page.Items {
			items = append(items, FromItem(item))
		}
		if len(page.LastEvaluatedKey) == 0 {
			return items, nil
		}
		input.ExclusiveStartKey = page.LastEvaluatedKey
	}
}
