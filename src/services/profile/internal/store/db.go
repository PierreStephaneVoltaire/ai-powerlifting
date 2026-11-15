package store

import (
	"context"
	"errors"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/profile/internal/value"
)

var (
	ErrConditionFailed     = errors.New("conditional check failed")
	ErrTransactionCanceled = errors.New("transaction canceled")
)

type API interface {
	GetItem(ctx context.Context, in *dynamodb.GetItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	PutItem(ctx context.Context, in *dynamodb.PutItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
	UpdateItem(ctx context.Context, in *dynamodb.UpdateItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
	DeleteItem(ctx context.Context, in *dynamodb.DeleteItemInput, opts ...func(*dynamodb.Options)) (*dynamodb.DeleteItemOutput, error)
	Query(ctx context.Context, in *dynamodb.QueryInput, opts ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	Scan(ctx context.Context, in *dynamodb.ScanInput, opts ...func(*dynamodb.Options)) (*dynamodb.ScanOutput, error)
	TransactWriteItems(ctx context.Context, in *dynamodb.TransactWriteItemsInput, opts ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}

type Tables struct {
	User          string
	Requests      string
	Notifications string
	Tags          string
	Health        string
	Sessions      string
	Competitions  string
	Videos        string
	SentIndex     string
	InboxIndex    string
	RosterIndex   string
}

type DB struct {
	API    API
	Tables Tables
}

type Key map[string]string

func (k Key) av() map[string]types.AttributeValue {
	out := make(map[string]types.AttributeValue, len(k))
	for name, v := range k {
		out[name] = &types.AttributeValueMemberS{Value: v}
	}
	return out
}

func PK(pk string) Key       { return Key{"pk": pk} }
func PKSK(pk, sk string) Key { return Key{"pk": pk, "sk": sk} }

func ptr[T any](v T) *T { return &v }

func nilIfEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func names(m map[string]string) map[string]string {
	if len(m) == 0 {
		return nil
	}
	return m
}

func values(m map[string]any) map[string]types.AttributeValue {
	if len(m) == 0 {
		return nil
	}
	return value.ToAV(m)
}

func translate(err error, op string) error {
	var conditional *types.ConditionalCheckFailedException
	if errors.As(err, &conditional) {
		return ErrConditionFailed
	}
	var canceled *types.TransactionCanceledException
	if errors.As(err, &canceled) {
		return ErrTransactionCanceled
	}
	return fmt.Errorf("%s: %w", op, err)
}

func (d *DB) Get(ctx context.Context, table string, key Key) (value.Item, error) {
	return d.GetProjected(ctx, table, key, "", nil)
}

func (d *DB) GetProjected(ctx context.Context, table string, key Key, projection string, aliases map[string]string) (value.Item, error) {
	out, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:                &table,
		Key:                      key.av(),
		ConsistentRead:           ptr(true),
		ProjectionExpression:     nilIfEmpty(projection),
		ExpressionAttributeNames: names(aliases),
	})
	if err != nil {
		return nil, translate(err, "get "+table)
	}
	if len(out.Item) == 0 {
		return nil, nil
	}
	return value.FromAV(out.Item), nil
}

func (d *DB) Put(ctx context.Context, table string, item value.Item, condition string) error {
	_, err := d.API.PutItem(ctx, &dynamodb.PutItemInput{TableName: &table, Item: value.ToAV(item), ConditionExpression: nilIfEmpty(condition)})
	if err != nil {
		return translate(err, "put "+table)
	}
	return nil
}

func (d *DB) Delete(ctx context.Context, table string, key Key) error {
	_, err := d.API.DeleteItem(ctx, &dynamodb.DeleteItemInput{TableName: &table, Key: key.av()})
	if err != nil {
		return translate(err, "delete "+table)
	}
	return nil
}

type Update struct {
	Expression string
	Condition  string
	Names      map[string]string
	Values     map[string]any
}

func (d *DB) Update(ctx context.Context, table string, key Key, update Update) error {
	_, err := d.API.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:                 &table,
		Key:                       key.av(),
		UpdateExpression:          &update.Expression,
		ConditionExpression:       nilIfEmpty(update.Condition),
		ExpressionAttributeNames:  names(update.Names),
		ExpressionAttributeValues: values(update.Values),
	})
	if err != nil {
		return translate(err, "update "+table)
	}
	return nil
}

type Query struct {
	Table      string
	Index      string
	KeyCond    string
	Filter     string
	Names      map[string]string
	Values     map[string]any
	Descending bool
	Consistent bool
}

func (d *DB) Query(ctx context.Context, q Query) ([]value.Item, error) {
	in := &dynamodb.QueryInput{
		TableName:                 &q.Table,
		IndexName:                 nilIfEmpty(q.Index),
		KeyConditionExpression:    &q.KeyCond,
		FilterExpression:          nilIfEmpty(q.Filter),
		ExpressionAttributeNames:  names(q.Names),
		ExpressionAttributeValues: values(q.Values),
	}
	if q.Descending {
		in.ScanIndexForward = ptr(false)
	}
	if q.Consistent {
		in.ConsistentRead = ptr(true)
	}
	var items []value.Item
	for {
		out, err := d.API.Query(ctx, in)
		if err != nil {
			return nil, translate(err, "query "+q.Table)
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

type Scan struct {
	Table      string
	Filter     string
	Names      map[string]string
	Values     map[string]any
	Consistent bool
}

func (d *DB) Scan(ctx context.Context, s Scan) ([]value.Item, error) {
	in := &dynamodb.ScanInput{
		TableName:                 &s.Table,
		FilterExpression:          nilIfEmpty(s.Filter),
		ExpressionAttributeNames:  names(s.Names),
		ExpressionAttributeValues: values(s.Values),
	}
	if s.Consistent {
		in.ConsistentRead = ptr(true)
	}
	var items []value.Item
	for {
		out, err := d.API.Scan(ctx, in)
		if err != nil {
			return nil, translate(err, "scan "+s.Table)
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

type WriteKind int

const (
	WritePut WriteKind = iota
	WriteUpdate
	WriteDelete
	WriteCheck
)

type Write struct {
	Kind      WriteKind
	Table     string
	Key       Key
	Item      value.Item
	Update    string
	Condition string
	Names     map[string]string
	Values    map[string]any
}

func (w Write) item() types.TransactWriteItem {
	switch w.Kind {
	case WritePut:
		return types.TransactWriteItem{Put: &types.Put{
			TableName:                 &w.Table,
			Item:                      value.ToAV(w.Item),
			ConditionExpression:       nilIfEmpty(w.Condition),
			ExpressionAttributeNames:  names(w.Names),
			ExpressionAttributeValues: values(w.Values),
		}}
	case WriteUpdate:
		return types.TransactWriteItem{Update: &types.Update{
			TableName:                 &w.Table,
			Key:                       w.Key.av(),
			UpdateExpression:          &w.Update,
			ConditionExpression:       nilIfEmpty(w.Condition),
			ExpressionAttributeNames:  names(w.Names),
			ExpressionAttributeValues: values(w.Values),
		}}
	case WriteDelete:
		return types.TransactWriteItem{Delete: &types.Delete{TableName: &w.Table, Key: w.Key.av()}}
	}
	return types.TransactWriteItem{ConditionCheck: &types.ConditionCheck{
		TableName:                 &w.Table,
		Key:                       w.Key.av(),
		ConditionExpression:       &w.Condition,
		ExpressionAttributeNames:  names(w.Names),
		ExpressionAttributeValues: values(w.Values),
	}}
}

func (d *DB) Transact(ctx context.Context, writes []Write) error {
	items := make([]types.TransactWriteItem, len(writes))
	for i, w := range writes {
		items[i] = w.item()
	}
	if _, err := d.API.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{TransactItems: items}); err != nil {
		return translate(err, "transact")
	}
	return nil
}
