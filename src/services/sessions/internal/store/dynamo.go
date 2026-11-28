package store

import (
	"context"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/sessions/internal/session"
	"powerlifting/sessions/internal/value"
)

const (
	batchSize     = 25
	batchAttempts = 6
	pointerSK     = "program#current"
)

type API interface {
	Query(ctx context.Context, in *dynamodb.QueryInput, opts ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	GetItem(ctx context.Context, in *dynamodb.GetItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	PutItem(ctx context.Context, in *dynamodb.PutItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
	DeleteItem(ctx context.Context, in *dynamodb.DeleteItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.DeleteItemOutput, error)
	BatchWriteItem(ctx context.Context, in *dynamodb.BatchWriteItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.BatchWriteItemOutput, error)
}

type Dynamo struct {
	API           API
	SessionsTable string
	HealthTable   string
	Sleep         func(time.Duration)
}

var listingFields = []string{"session_id", "id", "sk", "date", "week_number", "block", "label", "name", "status", "completed", "exercises", "same_day_ordinal", "program_sk"}

func key(pk, sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: pk}, "sk": &types.AttributeValueMemberS{Value: sk}}
}

func (d *Dynamo) query(ctx context.Context, in *dynamodb.QueryInput) ([]value.Item, error) {
	in.TableName = &d.SessionsTable
	in.ConsistentRead = ptr(true)
	var items []value.Item
	for {
		out, err := d.API.Query(ctx, in)
		if err != nil {
			return nil, fmt.Errorf("query sessions: %w", err)
		}
		for _, raw := range out.Items {
			items = append(items, value.FromAV(raw))
		}
		if len(out.LastEvaluatedKey) == 0 {
			return items, nil
		}
		in.ExclusiveStartKey = out.LastEvaluatedKey
	}
}

func (d *Dynamo) ForProgram(ctx context.Context, pk, programSK string) ([]value.Item, error) {
	return d.query(ctx, &dynamodb.QueryInput{
		KeyConditionExpression: ptr("pk = :pk AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":     &types.AttributeValueMemberS{Value: pk},
			":prefix": &types.AttributeValueMemberS{Value: "session#" + programSK + "#"},
		},
	})
}

func (d *Dynamo) Listing(ctx context.Context, pk, programSK string) ([]value.Item, error) {
	names := map[string]string{"#program": "program_sk"}
	projection := ""
	for i, field := range listingFields {
		alias := fmt.Sprintf("#f%d", i)
		names[alias] = field
		if i > 0 {
			projection += ","
		}
		projection += alias
	}
	return d.query(ctx, &dynamodb.QueryInput{
		KeyConditionExpression:   ptr("pk = :pk"),
		FilterExpression:         ptr("#program = :program"),
		ProjectionExpression:     &projection,
		ExpressionAttributeNames: names,
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":      &types.AttributeValueMemberS{Value: pk},
			":program": &types.AttributeValueMemberS{Value: programSK},
		},
		ScanIndexForward: ptr(false),
	})
}

func (d *Dynamo) CurrentBlockExercises(ctx context.Context, pk, programSK string) ([]value.Item, error) {
	return d.query(ctx, &dynamodb.QueryInput{
		KeyConditionExpression: ptr("pk = :pk AND begins_with(sk, :prefix)"),
		FilterExpression:       ptr("(attribute_not_exists(#block) OR #block = :current) AND size(#exercises) > :zero"),
		ProjectionExpression:   ptr("#date, #exercises, #completed, #session_id, #id"),
		ExpressionAttributeNames: map[string]string{
			"#block":      "block",
			"#date":       "date",
			"#exercises":  "exercises",
			"#completed":  "completed",
			"#session_id": "session_id",
			"#id":         "id",
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":      &types.AttributeValueMemberS{Value: pk},
			":prefix":  &types.AttributeValueMemberS{Value: "session#" + programSK + "#"},
			":current": &types.AttributeValueMemberS{Value: "current"},
			":zero":    &types.AttributeValueMemberN{Value: "0"},
		},
		ScanIndexForward: ptr(false),
	})
}

func (d *Dynamo) Put(ctx context.Context, item value.Item) error {
	_, err := d.API.PutItem(ctx, &dynamodb.PutItemInput{TableName: &d.SessionsTable, Item: value.ToAV(item)})
	if err != nil {
		return fmt.Errorf("put session: %w", err)
	}
	return nil
}

func (d *Dynamo) Delete(ctx context.Context, pk, sk string) error {
	_, err := d.API.DeleteItem(ctx, &dynamodb.DeleteItemInput{TableName: &d.SessionsTable, Key: key(pk, sk)})
	if err != nil {
		return fmt.Errorf("delete session: %w", err)
	}
	return nil
}

func (d *Dynamo) Apply(ctx context.Context, pk string, deleteSKs []string, puts []value.Item) error {
	var requests []types.WriteRequest
	for _, sk := range deleteSKs {
		requests = append(requests, types.WriteRequest{DeleteRequest: &types.DeleteRequest{Key: key(pk, sk)}})
	}
	for _, item := range puts {
		requests = append(requests, types.WriteRequest{PutRequest: &types.PutRequest{Item: value.ToAV(item)}})
	}
	for start := 0; start < len(requests); start += batchSize {
		if err := d.writeBatch(ctx, requests[start:min(start+batchSize, len(requests))]); err != nil {
			return err
		}
	}
	return nil
}

func (d *Dynamo) writeBatch(ctx context.Context, batch []types.WriteRequest) error {
	pending := map[string][]types.WriteRequest{d.SessionsTable: batch}
	for attempt := 0; attempt < batchAttempts; attempt++ {
		out, err := d.API.BatchWriteItem(ctx, &dynamodb.BatchWriteItemInput{RequestItems: pending})
		if err != nil {
			return fmt.Errorf("batch write sessions: %w", err)
		}
		if len(out.UnprocessedItems) == 0 {
			return nil
		}
		pending = out.UnprocessedItems
		if d.Sleep != nil {
			d.Sleep(time.Duration(50<<attempt) * time.Millisecond)
		}
	}
	return fmt.Errorf("batch write sessions: unprocessed items remain")
}

func (d *Dynamo) get(ctx context.Context, sk, pk string, projection *string, names map[string]string) (map[string]types.AttributeValue, error) {
	out, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:                &d.HealthTable,
		Key:                      key(pk, sk),
		ConsistentRead:           ptr(true),
		ProjectionExpression:     projection,
		ExpressionAttributeNames: names,
	})
	if err != nil {
		return nil, fmt.Errorf("get program: %w", err)
	}
	return out.Item, nil
}

func (d *Dynamo) CurrentSK(ctx context.Context, pk string) (string, error) {
	item, err := d.get(ctx, pointerSK, pk, ptr("ref_sk"), nil)
	if err != nil {
		return "", err
	}
	if ref, ok := value.FromAV(item)["ref_sk"].(string); ok && ref != "" {
		return ref, nil
	}
	return "", nil
}

func (d *Dynamo) Program(ctx context.Context, pk, sk string) (session.Program, error) {
	item, err := d.get(ctx, sk, pk, ptr("phases"), nil)
	if err != nil {
		return session.Program{}, err
	}
	if item == nil {
		return session.Program{}, nil
	}
	decoded := value.FromAV(item)
	program := session.Program{Found: true}
	if phases, ok := decoded["phases"].([]any); ok {
		program.Phases = phases
	}
	return program, nil
}

func ptr[T any](v T) *T { return &v }
