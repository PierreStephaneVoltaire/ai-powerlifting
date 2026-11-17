package store

import (
	"context"
	"errors"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Store struct {
	DB    *dynamodb.Client
	Table string
}

var ErrConflict = errors.New("Weight Log changed; reload before retrying")

func (s Store) Get(ctx context.Context, pk, sk string) (map[string]any, error) {
	result, err := s.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(s.Table), Key: ToItem(map[string]any{"pk": pk, "sk": sk})})
	if err != nil {
		return nil, err
	}
	if len(result.Item) == 0 {
		return nil, nil
	}
	return FromItem(result.Item), nil
}
func (s Store) Put(ctx context.Context, item map[string]any, previous string) error {
	_, err := s.DB.PutItem(ctx, &dynamodb.PutItemInput{TableName: aws.String(s.Table), Item: ToItem(item), ConditionExpression: aws.String("attribute_not_exists(updated_at) OR updated_at = :previous"), ExpressionAttributeValues: map[string]types.AttributeValue{":previous": &types.AttributeValueMemberS{Value: previous}}})
	var conflict *types.ConditionalCheckFailedException
	if errors.As(err, &conflict) {
		return ErrConflict
	}
	return err
}
