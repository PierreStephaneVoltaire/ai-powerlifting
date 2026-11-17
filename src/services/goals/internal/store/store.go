package store

import (
	"context"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Store struct {
	DB    *dynamodb.Client
	Table string
}

func (s Store) List(ctx context.Context, pk string) ([]map[string]any, error) {
	out := []map[string]any{}
	var start map[string]types.AttributeValue
	for {
		result, err := s.DB.Query(ctx, &dynamodb.QueryInput{TableName: aws.String(s.Table), KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :prefix)"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}, ":prefix": &types.AttributeValueMemberS{Value: "GOAL#"}}, ExclusiveStartKey: start})
		if err != nil {
			return nil, err
		}
		for _, item := range result.Items {
			out = append(out, FromItem(item))
		}
		start = result.LastEvaluatedKey
		if len(start) == 0 {
			return out, nil
		}
	}
}
func (s Store) Put(ctx context.Context, item map[string]any) error {
	_, err := s.DB.PutItem(ctx, &dynamodb.PutItemInput{TableName: aws.String(s.Table), Item: ToItem(item)})
	return err
}
func (s Store) Delete(ctx context.Context, pk, id string) error {
	_, err := s.DB.DeleteItem(ctx, &dynamodb.DeleteItemInput{TableName: aws.String(s.Table), Key: ToItem(map[string]any{"pk": pk, "sk": "GOAL#" + id})})
	return err
}
