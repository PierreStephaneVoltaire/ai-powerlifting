package store

import (
	"context"
	"fmt"
	"strings"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type API interface {
	GetItem(ctx context.Context, input *dynamodb.GetItemInput, options ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	PutItem(ctx context.Context, input *dynamodb.PutItemInput, options ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
	Query(ctx context.Context, input *dynamodb.QueryInput, options ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	BatchWriteItem(ctx context.Context, input *dynamodb.BatchWriteItemInput, options ...func(*dynamodb.Options)) (*dynamodb.BatchWriteItemOutput, error)
}

type AWS struct{ API API }

const batchSize = 25

func keyAttrs(key Key) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: key.PK}, "sk": &types.AttributeValueMemberS{Value: key.SK}}
}

func (a AWS) Get(ctx context.Context, table Table, key Key, options GetOptions) (Item, error) {
	name := string(table)
	input := &dynamodb.GetItemInput{TableName: &name, Key: keyAttrs(key)}
	if options.Consistent {
		consistent := true
		input.ConsistentRead = &consistent
	}
	if len(options.Projection) > 0 {
		names := map[string]string{}
		expressions := make([]string, 0, len(options.Projection))
		for _, path := range options.Projection {
			parts := strings.Split(path, ".")
			aliased := make([]string, len(parts))
			for index, part := range parts {
				alias := "#" + part
				names[alias] = part
				aliased[index] = alias
			}
			expressions = append(expressions, strings.Join(aliased, "."))
		}
		expression := strings.Join(expressions, ", ")
		input.ProjectionExpression = &expression
		input.ExpressionAttributeNames = names
	}
	output, err := a.API.GetItem(ctx, input)
	if err != nil {
		return nil, err
	}
	if output.Item == nil {
		return nil, nil
	}
	return FromAttrMap(output.Item), nil
}

func (a AWS) Put(ctx context.Context, table Table, item Item) error {
	name := string(table)
	attrs, err := ToAttrMap(item)
	if err != nil {
		return err
	}
	_, err = a.API.PutItem(ctx, &dynamodb.PutItemInput{TableName: &name, Item: attrs})
	return err
}

func (a AWS) Query(ctx context.Context, query Query) ([]Item, error) {
	name := string(table(query))
	pkAttr, skAttr := query.pkAttr(), query.skAttr()
	names := map[string]string{"#pk": pkAttr}
	values := map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: query.PK}}
	condition := "#pk = :pk"
	switch {
	case query.Between != nil:
		names["#sk"] = skAttr
		values[":lo"] = &types.AttributeValueMemberS{Value: query.Between[0]}
		values[":hi"] = &types.AttributeValueMemberS{Value: query.Between[1]}
		condition += " AND #sk BETWEEN :lo AND :hi"
	case query.AtLeast != "":
		names["#sk"] = skAttr
		values[":lo"] = &types.AttributeValueMemberS{Value: query.AtLeast}
		condition += " AND #sk >= :lo"
	case query.AtMost != "":
		names["#sk"] = skAttr
		values[":hi"] = &types.AttributeValueMemberS{Value: query.AtMost}
		condition += " AND #sk <= :hi"
	case query.Prefix != "":
		names["#sk"] = skAttr
		values[":prefix"] = &types.AttributeValueMemberS{Value: query.Prefix}
		condition += " AND begins_with(#sk, :prefix)"
	}
	input := &dynamodb.QueryInput{
		TableName:                 &name,
		KeyConditionExpression:    &condition,
		ExpressionAttributeNames:  names,
		ExpressionAttributeValues: values,
	}
	if query.Index != "" {
		index := query.Index
		input.IndexName = &index
	}
	if query.Consistent && query.Index == "" {
		consistent := true
		input.ConsistentRead = &consistent
	}
	var items []Item
	for {
		output, err := a.API.Query(ctx, input)
		if err != nil {
			return nil, err
		}
		for _, raw := range output.Items {
			items = append(items, FromAttrMap(raw))
		}
		if len(output.LastEvaluatedKey) == 0 {
			return items, nil
		}
		input.ExclusiveStartKey = output.LastEvaluatedKey
	}
}

func table(query Query) Table { return query.Table }

func (a AWS) BatchPut(ctx context.Context, table Table, items []Item) error {
	requests := make([]types.WriteRequest, 0, len(items))
	for _, item := range items {
		attrs, err := ToAttrMap(item)
		if err != nil {
			return err
		}
		requests = append(requests, types.WriteRequest{PutRequest: &types.PutRequest{Item: attrs}})
	}
	return a.batch(ctx, table, requests)
}

func (a AWS) BatchDelete(ctx context.Context, table Table, keys []Key) error {
	requests := make([]types.WriteRequest, 0, len(keys))
	for _, key := range keys {
		requests = append(requests, types.WriteRequest{DeleteRequest: &types.DeleteRequest{Key: keyAttrs(key)}})
	}
	return a.batch(ctx, table, requests)
}

func (a AWS) batch(ctx context.Context, table Table, requests []types.WriteRequest) error {
	name := string(table)
	for start := 0; start < len(requests); start += batchSize {
		end := min(start+batchSize, len(requests))
		pending := map[string][]types.WriteRequest{name: requests[start:end]}
		for attempt := 0; len(pending) > 0; attempt++ {
			if attempt > 8 {
				return fmt.Errorf("batch write left unprocessed items in %s", name)
			}
			output, err := a.API.BatchWriteItem(ctx, &dynamodb.BatchWriteItemInput{RequestItems: pending})
			if err != nil {
				return err
			}
			pending = output.UnprocessedItems
		}
	}
	return nil
}
