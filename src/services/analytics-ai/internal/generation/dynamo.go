package generation

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type API interface {
	GetItem(ctx context.Context, input *dynamodb.GetItemInput, options ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	PutItem(ctx context.Context, input *dynamodb.PutItemInput, options ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
	UpdateItem(ctx context.Context, input *dynamodb.UpdateItemInput, options ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
}

type Dynamo struct {
	API   API
	Table string
}

func key(pk, sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: pk}, "sk": &types.AttributeValueMemberS{Value: sk}}
}

func number(value int) types.AttributeValue {
	return &types.AttributeValueMemberN{Value: fmt.Sprint(value)}
}

func conditionFailed(err error) bool {
	var failed *types.ConditionalCheckFailedException
	return errors.As(err, &failed)
}

func (d Dynamo) Get(ctx context.Context, pk, sk string) (Item, error) {
	output, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{TableName: &d.Table, Key: key(pk, sk), ConsistentRead: boolean(true)})
	if err != nil {
		return nil, err
	}
	if len(output.Item) == 0 {
		return nil, nil
	}
	var item Item
	if err := attributevalue.UnmarshalMap(output.Item, &item); err != nil {
		return nil, err
	}
	return item, nil
}

func (d Dynamo) put(ctx context.Context, item Item, input *dynamodb.PutItemInput) (bool, error) {
	marshaled, err := attributevalue.MarshalMap(item)
	if err != nil {
		return false, err
	}
	input.TableName = &d.Table
	input.Item = marshaled
	if _, err := d.API.PutItem(ctx, input); err != nil {
		if conditionFailed(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func (d Dynamo) PutIfAbsent(ctx context.Context, item Item) (bool, error) {
	condition := "attribute_not_exists(pk)"
	return d.put(ctx, item, &dynamodb.PutItemInput{ConditionExpression: &condition})
}

func (d Dynamo) PutIfCurrent(ctx context.Context, item Item, status string, attempt int) (bool, error) {
	condition := "#status=:previous AND attempt=:attempt"
	return d.put(ctx, item, &dynamodb.PutItemInput{
		ConditionExpression:       &condition,
		ExpressionAttributeNames:  map[string]string{"#status": "status"},
		ExpressionAttributeValues: map[string]types.AttributeValue{":previous": &types.AttributeValueMemberS{Value: status}, ":attempt": number(attempt)},
	})
}

func (d Dynamo) Put(ctx context.Context, item Item) error {
	_, err := d.put(ctx, item, &dynamodb.PutItemInput{})
	return err
}

func (d Dynamo) Update(ctx context.Context, pk, sk string, attempt int, fields Item) error {
	names := map[string]string{"#attempt": "attempt"}
	values := map[string]types.AttributeValue{":attempt": number(attempt)}
	fieldNames := make([]string, 0, len(fields))
	for name := range fields {
		fieldNames = append(fieldNames, name)
	}
	sort.Strings(fieldNames)
	assignments := make([]string, 0, len(fields))
	for index, name := range fieldNames {
		value, err := attributevalue.Marshal(fields[name])
		if err != nil {
			return err
		}
		names[fmt.Sprintf("#f%d", index)] = name
		values[fmt.Sprintf(":v%d", index)] = value
		assignments = append(assignments, fmt.Sprintf("#f%d=:v%d", index, index))
	}
	expression := "SET " + strings.Join(assignments, ", ")
	condition := "#attempt=:attempt"
	_, err := d.API.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:                 &d.Table,
		Key:                       key(pk, sk),
		UpdateExpression:          &expression,
		ConditionExpression:       &condition,
		ExpressionAttributeNames:  names,
		ExpressionAttributeValues: values,
	})
	if err != nil && !conditionFailed(err) {
		return err
	}
	return nil
}

func boolean(value bool) *bool { return &value }
