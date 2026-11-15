package fakedb

import (
	"context"
	"fmt"
	"slices"
	"strings"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/profile/internal/value"
)

type Index struct{ Hash, Range string }

type Schema struct {
	Hash, Range string
	Indexes     map[string]Index
}

type DB struct {
	mu     sync.Mutex
	Schema map[string]Schema
	tables map[string]map[string]attrs
	Calls  map[string]int
}

func New(schema map[string]Schema) *DB {
	d := &DB{Schema: schema, tables: map[string]map[string]attrs{}, Calls: map[string]int{}}
	for name := range schema {
		d.tables[name] = map[string]attrs{}
	}
	return d
}

func (d *DB) keyOf(table string, item attrs) string {
	schema := d.Schema[table]
	key := avString(item[schema.Hash])
	if schema.Range != "" {
		key += "\x00" + avString(item[schema.Range])
	}
	return key
}

func avString(v types.AttributeValue) string {
	if s, ok := v.(*types.AttributeValueMemberS); ok {
		return s.Value
	}
	return ""
}

func copyAttrs(item attrs) attrs {
	out := make(attrs, len(item))
	for key, v := range item {
		out[key] = copyValue(v)
	}
	return out
}

func copyValue(v types.AttributeValue) types.AttributeValue {
	switch typed := v.(type) {
	case *types.AttributeValueMemberL:
		list := make([]types.AttributeValue, len(typed.Value))
		for i, child := range typed.Value {
			list[i] = copyValue(child)
		}
		return &types.AttributeValueMemberL{Value: list}
	case *types.AttributeValueMemberM:
		return &types.AttributeValueMemberM{Value: copyAttrs(typed.Value)}
	case *types.AttributeValueMemberSS:
		return &types.AttributeValueMemberSS{Value: append([]string(nil), typed.Value...)}
	case *types.AttributeValueMemberNS:
		return &types.AttributeValueMemberNS{Value: append([]string(nil), typed.Value...)}
	}
	return v
}

func (d *DB) Seed(table string, items ...value.Item) {
	d.mu.Lock()
	defer d.mu.Unlock()
	for _, item := range items {
		av := value.ToAV(item)
		d.tables[table][d.keyOf(table, av)] = av
	}
}

func (d *DB) Items(table string) []value.Item {
	d.mu.Lock()
	defer d.mu.Unlock()
	keys := make([]string, 0, len(d.tables[table]))
	for key := range d.tables[table] {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	out := make([]value.Item, 0, len(keys))
	for _, key := range keys {
		out = append(out, value.FromAV(d.tables[table][key]))
	}
	return out
}

func (d *DB) Count(call string) int {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.Calls[call]
}

func (d *DB) table(name *string) (string, error) {
	if name == nil {
		return "", fmt.Errorf("table name missing")
	}
	if _, ok := d.tables[*name]; !ok {
		return "", fmt.Errorf("unknown table %s", *name)
	}
	return *name, nil
}

func envOf(names map[string]string, values map[string]types.AttributeValue) env {
	return env{names: names, values: values}
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func project(item attrs, projection *string, names map[string]string) attrs {
	if projection == nil {
		return copyAttrs(item)
	}
	out := attrs{}
	for _, part := range strings.Split(*projection, ",") {
		part = strings.TrimSpace(part)
		if resolved, ok := names[part]; ok {
			part = resolved
		}
		if v, ok := item[part]; ok {
			out[part] = v
		}
	}
	return copyAttrs(out)
}

func (d *DB) GetItem(_ context.Context, in *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["GetItem"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	item, ok := d.tables[table][d.keyOf(table, in.Key)]
	if !ok {
		return &dynamodb.GetItemOutput{}, nil
	}
	return &dynamodb.GetItemOutput{Item: project(item, in.ProjectionExpression, in.ExpressionAttributeNames)}, nil
}

func (d *DB) check(table string, existing attrs, condition *string, names map[string]string, values map[string]types.AttributeValue) error {
	if condition == nil {
		return nil
	}
	if existing == nil {
		existing = attrs{}
	}
	ok, err := evalCondition(*condition, envOf(names, values), existing)
	if err != nil {
		return err
	}
	if !ok {
		return &types.ConditionalCheckFailedException{}
	}
	return nil
}

func (d *DB) PutItem(_ context.Context, in *dynamodb.PutItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["PutItem"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	key := d.keyOf(table, in.Item)
	if err := d.check(table, d.tables[table][key], in.ConditionExpression, in.ExpressionAttributeNames, in.ExpressionAttributeValues); err != nil {
		return nil, err
	}
	d.tables[table][key] = copyAttrs(in.Item)
	return &dynamodb.PutItemOutput{}, nil
}

func (d *DB) applyUpdate(table string, key attrs, expression string, names map[string]string, values map[string]types.AttributeValue) error {
	k := d.keyOf(table, key)
	item, ok := d.tables[table][k]
	if !ok {
		item = attrs{}
		for name, v := range key {
			item[name] = v
		}
	}
	next := copyAttrs(item)
	if err := applyUpdate(expression, envOf(names, values), next); err != nil {
		return err
	}
	d.tables[table][k] = next
	return nil
}

func (d *DB) UpdateItem(_ context.Context, in *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["UpdateItem"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	if err := d.check(table, d.tables[table][d.keyOf(table, in.Key)], in.ConditionExpression, in.ExpressionAttributeNames, in.ExpressionAttributeValues); err != nil {
		return nil, err
	}
	if err := d.applyUpdate(table, in.Key, str(in.UpdateExpression), in.ExpressionAttributeNames, in.ExpressionAttributeValues); err != nil {
		return nil, err
	}
	return &dynamodb.UpdateItemOutput{}, nil
}

func (d *DB) DeleteItem(_ context.Context, in *dynamodb.DeleteItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.DeleteItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["DeleteItem"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	delete(d.tables[table], d.keyOf(table, in.Key))
	return &dynamodb.DeleteItemOutput{}, nil
}

func (d *DB) candidates(table, index string) ([]attrs, string, error) {
	schema := d.Schema[table]
	hash, rng := schema.Hash, schema.Range
	if index != "" {
		idx, ok := schema.Indexes[index]
		if !ok {
			return nil, "", fmt.Errorf("unknown index %s", index)
		}
		hash, rng = idx.Hash, idx.Range
	}
	var rows []attrs
	for _, item := range d.tables[table] {
		if _, ok := item[hash]; !ok {
			continue
		}
		if rng != "" {
			if _, ok := item[rng]; !ok {
				continue
			}
		}
		rows = append(rows, item)
	}
	slices.SortFunc(rows, func(a, b attrs) int {
		if rng != "" {
			if c := strings.Compare(avString(a[rng]), avString(b[rng])); c != 0 {
				return c
			}
		}
		return strings.Compare(d.keyOf(table, a), d.keyOf(table, b))
	})
	return rows, rng, nil
}

func (d *DB) Query(_ context.Context, in *dynamodb.QueryInput, _ ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["Query"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	rows, _, err := d.candidates(table, str(in.IndexName))
	if err != nil {
		return nil, err
	}
	if in.ScanIndexForward != nil && !*in.ScanIndexForward {
		slices.Reverse(rows)
	}
	e := envOf(in.ExpressionAttributeNames, in.ExpressionAttributeValues)
	out := &dynamodb.QueryOutput{}
	for _, row := range rows {
		ok, err := evalCondition(str(in.KeyConditionExpression), e, row)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		if in.FilterExpression != nil {
			if ok, err = evalCondition(*in.FilterExpression, e, row); err != nil {
				return nil, err
			} else if !ok {
				continue
			}
		}
		out.Items = append(out.Items, project(row, in.ProjectionExpression, in.ExpressionAttributeNames))
	}
	return out, nil
}

func (d *DB) Scan(_ context.Context, in *dynamodb.ScanInput, _ ...func(*dynamodb.Options)) (*dynamodb.ScanOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["Scan"]++
	table, err := d.table(in.TableName)
	if err != nil {
		return nil, err
	}
	rows, _, err := d.candidates(table, "")
	if err != nil {
		return nil, err
	}
	e := envOf(in.ExpressionAttributeNames, in.ExpressionAttributeValues)
	out := &dynamodb.ScanOutput{}
	for _, row := range rows {
		if in.FilterExpression != nil {
			ok, err := evalCondition(*in.FilterExpression, e, row)
			if err != nil {
				return nil, err
			}
			if !ok {
				continue
			}
		}
		out.Items = append(out.Items, copyAttrs(row))
	}
	return out, nil
}

func (d *DB) TransactWriteItems(_ context.Context, in *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.Calls["TransactWriteItems"]++
	for _, w := range in.TransactItems {
		switch {
		case w.Put != nil:
			table, err := d.table(w.Put.TableName)
			if err != nil {
				return nil, err
			}
			if err := d.check(table, d.tables[table][d.keyOf(table, w.Put.Item)], w.Put.ConditionExpression, w.Put.ExpressionAttributeNames, w.Put.ExpressionAttributeValues); err != nil {
				return nil, &types.TransactionCanceledException{}
			}
		case w.Update != nil:
			table, err := d.table(w.Update.TableName)
			if err != nil {
				return nil, err
			}
			if err := d.check(table, d.tables[table][d.keyOf(table, w.Update.Key)], w.Update.ConditionExpression, w.Update.ExpressionAttributeNames, w.Update.ExpressionAttributeValues); err != nil {
				return nil, &types.TransactionCanceledException{}
			}
		case w.ConditionCheck != nil:
			table, err := d.table(w.ConditionCheck.TableName)
			if err != nil {
				return nil, err
			}
			if err := d.check(table, d.tables[table][d.keyOf(table, w.ConditionCheck.Key)], w.ConditionCheck.ConditionExpression, w.ConditionCheck.ExpressionAttributeNames, w.ConditionCheck.ExpressionAttributeValues); err != nil {
				return nil, &types.TransactionCanceledException{}
			}
		}
	}
	for _, w := range in.TransactItems {
		switch {
		case w.Put != nil:
			table, _ := d.table(w.Put.TableName)
			d.tables[table][d.keyOf(table, w.Put.Item)] = copyAttrs(w.Put.Item)
		case w.Update != nil:
			table, _ := d.table(w.Update.TableName)
			if err := d.applyUpdate(table, w.Update.Key, str(w.Update.UpdateExpression), w.Update.ExpressionAttributeNames, w.Update.ExpressionAttributeValues); err != nil {
				return nil, err
			}
		case w.Delete != nil:
			table, _ := d.table(w.Delete.TableName)
			delete(d.tables[table], d.keyOf(table, w.Delete.Key))
		}
	}
	return &dynamodb.TransactWriteItemsOutput{}, nil
}
