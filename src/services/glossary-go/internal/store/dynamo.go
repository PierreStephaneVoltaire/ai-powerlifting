package store

import (
	"context"
	"errors"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type API interface {
	GetItem(ctx context.Context, input *dynamodb.GetItemInput, options ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(ctx context.Context, input *dynamodb.QueryInput, options ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	UpdateItem(ctx context.Context, input *dynamodb.UpdateItemInput, options ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
	TransactWriteItems(ctx context.Context, input *dynamodb.TransactWriteItemsInput, options ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}

type Dynamo struct {
	API   API
	Table string
}

func keyAttributes(key Key) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: key.PK}, "sk": &types.AttributeValueMemberS{Value: key.SK}}
}

func decode(raw map[string]types.AttributeValue) (Item, error) {
	item := Item{}
	if err := attributevalue.UnmarshalMap(raw, &item); err != nil {
		return nil, err
	}
	delete(item, "pk")
	delete(item, "sk")
	return item, nil
}

func (d Dynamo) Get(ctx context.Context, key Key) (Item, error) {
	output, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{TableName: &d.Table, Key: keyAttributes(key), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return nil, err
	}
	if output.Item == nil {
		return nil, nil
	}
	return decode(output.Item)
}

func (d Dynamo) List(ctx context.Context, pk string) ([]Item, error) {
	paginator := dynamodb.NewQueryPaginator(d.API, &dynamodb.QueryInput{
		TableName:                 &d.Table,
		KeyConditionExpression:    aws.String("pk = :pk"),
		ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}},
	})
	var items []Item
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, err
		}
		for _, raw := range page.Items {
			item, err := decode(raw)
			if err != nil {
				return nil, err
			}
			items = append(items, item)
		}
	}
	return items, nil
}

func (d Dynamo) Update(ctx context.Context, key Key, patch Patch) error {
	if len(patch.Set) == 0 && len(patch.Remove) == 0 {
		return nil
	}
	names := map[string]string{}
	values := map[string]types.AttributeValue{}
	var sets, removes string
	index := 0
	for field, value := range patch.Set {
		encoded, err := attributevalue.Marshal(value)
		if err != nil {
			return err
		}
		name, placeholder := fmt.Sprintf("#s%d", index), fmt.Sprintf(":s%d", index)
		names[name], values[placeholder] = field, encoded
		sets += separator(sets) + name + " = " + placeholder
		index++
	}
	for _, field := range patch.Remove {
		name := fmt.Sprintf("#r%d", index)
		names[name] = field
		removes += separator(removes) + name
		index++
	}
	expression := ""
	if sets != "" {
		expression += "SET " + sets
	}
	if removes != "" {
		expression += " REMOVE " + removes
	}
	input := &dynamodb.UpdateItemInput{TableName: &d.Table, Key: keyAttributes(key), UpdateExpression: &expression, ExpressionAttributeNames: names}
	if len(values) > 0 {
		input.ExpressionAttributeValues = values
	}
	_, err := d.API.UpdateItem(ctx, input)
	return err
}

func separator(current string) string {
	if current == "" {
		return ""
	}
	return ", "
}

func (d Dynamo) CreateCatalog(ctx context.Context, item Item) (bool, error) {
	id, _ := item["id"].(string)
	nameKey, _ := item["name_key"].(string)
	body, err := attributevalue.MarshalMap(item)
	if err != nil {
		return false, err
	}
	for name, value := range keyAttributes(CatalogKey(id)) {
		body[name] = value
	}
	lookup := keyAttributes(Key{catalogNamePK, nameKey})
	lookup["id"] = &types.AttributeValueMemberS{Value: id}
	absent := aws.String("attribute_not_exists(pk)")
	_, err = d.API.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{TransactItems: []types.TransactWriteItem{
		{Put: &types.Put{TableName: &d.Table, Item: body, ConditionExpression: absent}},
		{Put: &types.Put{TableName: &d.Table, Item: lookup, ConditionExpression: absent}},
	}})
	var canceled *types.TransactionCanceledException
	if errors.As(err, &canceled) {
		return false, nil
	}
	return err == nil, err
}

func (d Dynamo) Pending(ctx context.Context, limit int) ([]Item, error) {
	output, err := d.API.Query(ctx, &dynamodb.QueryInput{
		TableName:                 &d.Table,
		IndexName:                 aws.String(genericIndex),
		KeyConditionExpression:    aws.String("generic_pending = :marker"),
		ExpressionAttributeValues: map[string]types.AttributeValue{":marker": &types.AttributeValueMemberS{Value: PendingMarker}},
		Limit:                     aws.Int32(int32(limit)),
	})
	if err != nil {
		return nil, err
	}
	items := make([]Item, 0, len(output.Items))
	for _, raw := range output.Items {
		item, err := decode(raw)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, nil
}
