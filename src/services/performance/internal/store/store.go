package store

import (
	"context"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Store struct {
	DB                      *dynamodb.Client
	Table, CompetitionTable string
}

func (s Store) Get(ctx context.Context, pk, sk string) (map[string]any, error) {
	r, e := s.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(s.Table), Key: ToItem(map[string]any{"pk": pk, "sk": sk}), ConsistentRead: aws.Bool(true)})
	if e != nil {
		return nil, e
	}
	if len(r.Item) == 0 {
		return nil, nil
	}
	return FromItem(r.Item), nil
}
func (s Store) Put(ctx context.Context, item map[string]any) error {
	_, e := s.DB.PutItem(ctx, &dynamodb.PutItemInput{TableName: aws.String(s.Table), Item: ToItem(item)})
	return e
}
func (s Store) Competitions(ctx context.Context, pk string) ([]map[string]any, error) {
	out := []map[string]any{}
	var start map[string]types.AttributeValue
	for {
		r, e := s.DB.Query(ctx, &dynamodb.QueryInput{TableName: aws.String(s.CompetitionTable), IndexName: aws.String("entries-by-date"), KeyConditionExpression: aws.String("pk = :pk"), ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}}, ExclusiveStartKey: start})
		if e != nil {
			return nil, e
		}
		for _, v := range r.Items {
			out = append(out, FromItem(v))
		}
		start = r.LastEvaluatedKey
		if len(start) == 0 {
			return out, nil
		}
	}
}
