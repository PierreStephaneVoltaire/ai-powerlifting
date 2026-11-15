package store

import (
	"context"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type API interface {
	GetItem(ctx context.Context, input *dynamodb.GetItemInput, options ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(ctx context.Context, input *dynamodb.QueryInput, options ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	UpdateItem(ctx context.Context, input *dynamodb.UpdateItemInput, options ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
}

type Tables struct {
	Entries  string
	Health   string
	Sessions string
	Glossary string
}

type Dynamo struct {
	API    API
	Tables Tables
}

func key(pk, sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{
		"pk": &types.AttributeValueMemberS{Value: pk},
		"sk": &types.AttributeValueMemberS{Value: sk},
	}
}

func (d Dynamo) get(ctx context.Context, table, pk, sk string, consistent bool) (Item, error) {
	out, err := d.API.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(table), Key: key(pk, sk), ConsistentRead: aws.Bool(consistent)})
	if err != nil {
		return nil, err
	}
	if len(out.Item) == 0 {
		return nil, nil
	}
	return FromItem(out.Item), nil
}

func (d Dynamo) query(ctx context.Context, table, index, pk, skPrefix string) ([]Item, error) {
	input := &dynamodb.QueryInput{
		TableName:                 aws.String(table),
		KeyConditionExpression:    aws.String("pk = :pk"),
		ExpressionAttributeValues: map[string]types.AttributeValue{":pk": &types.AttributeValueMemberS{Value: pk}},
	}
	if index != "" {
		input.IndexName = aws.String(index)
	}
	if skPrefix != "" {
		input.KeyConditionExpression = aws.String("pk = :pk AND begins_with(sk, :prefix)")
		input.ExpressionAttributeValues[":prefix"] = &types.AttributeValueMemberS{Value: skPrefix}
	}
	var items []Item
	for {
		out, err := d.API.Query(ctx, input)
		if err != nil {
			return nil, err
		}
		for _, raw := range out.Items {
			items = append(items, FromItem(raw))
		}
		if len(out.LastEvaluatedKey) == 0 {
			return items, nil
		}
		input.ExclusiveStartKey = out.LastEvaluatedKey
	}
}

func (d Dynamo) Get(ctx context.Context, pk, sk string) (Item, error) {
	return d.get(ctx, d.Tables.Entries, pk, sk, true)
}

func (d Dynamo) Query(ctx context.Context, pk, skPrefix string) ([]Item, error) {
	return d.query(ctx, d.Tables.Entries, "", pk, skPrefix)
}

func (d Dynamo) QueryByDate(ctx context.Context, pk string) ([]Item, error) {
	return d.query(ctx, d.Tables.Entries, EntriesByDate, pk, "")
}

func UpdateExpression(update EntryUpdate) (string, map[string]string, map[string]types.AttributeValue) {
	names := map[string]string{"#updated_at": "updated_at"}
	values := map[string]types.AttributeValue{":updated": &types.AttributeValueMemberS{Value: update.UpdatedAt}}
	sets := []string{"#updated_at = :updated"}
	for _, field := range update.Remove {
		names["#"+field] = field
	}
	for _, field := range update.Set {
		names["#"+field.Name] = field.Name
		values[":value_"+field.Name] = ToAttr(field.Value)
		sets = append(sets, "#"+field.Name+" = :value_"+field.Name)
	}
	expression := "SET " + strings.Join(sets, ", ")
	if len(update.Remove) > 0 {
		removes := make([]string, len(update.Remove))
		for index, field := range update.Remove {
			removes[index] = "#" + field
		}
		expression += " REMOVE " + strings.Join(removes, ", ")
	}
	return expression, names, values
}

func (d Dynamo) Update(ctx context.Context, pk, sk string, update EntryUpdate) error {
	expression, names, values := UpdateExpression(update)
	_, err := d.API.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:                 aws.String(d.Tables.Entries),
		Key:                       key(pk, sk),
		UpdateExpression:          aws.String(expression),
		ExpressionAttributeNames:  names,
		ExpressionAttributeValues: values,
	})
	return err
}

const projectionExpression = "SET projected_at_t_minus_1w = :projection, projection_snapshot_date = :snapshot, updated_at = :now"

func (d Dynamo) SaveProjection(ctx context.Context, pk, sk string, projection Projection) error {
	fields := make(map[string]types.AttributeValue, len(projection.Values))
	for _, field := range projection.Values {
		fields[field.Name] = ToAttr(field.Value)
	}
	_, err := d.API.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:        aws.String(d.Tables.Entries),
		Key:              key(pk, sk),
		UpdateExpression: aws.String(projectionExpression),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":projection": &types.AttributeValueMemberM{Value: fields},
			":snapshot":   &types.AttributeValueMemberS{Value: projection.SnapshotDate},
			":now":        &types.AttributeValueMemberS{Value: projection.UpdatedAt},
		},
	})
	return err
}

func (d Dynamo) Pointer(ctx context.Context, pk string) (Item, error) {
	return d.get(ctx, d.Tables.Health, pk, PointerSK, false)
}

func (d Dynamo) Item(ctx context.Context, pk, sk string) (Item, error) {
	return d.get(ctx, d.Tables.Health, pk, sk, false)
}

func (d Dynamo) GlossaryEntries(ctx context.Context, pk string) ([]Item, error) {
	return d.query(ctx, d.Tables.Glossary, "", pk, GlossarySKPrefix)
}

func (d Dynamo) Versions(ctx context.Context, pk string) ([]Item, error) {
	return d.query(ctx, d.Tables.Health, "", pk, ProgramSKPrefix)
}

func (d Dynamo) Sessions(ctx context.Context, pk, programSK string) ([]Item, error) {
	return d.query(ctx, d.Tables.Sessions, "", pk, SessionSKPrefix+programSK+"#")
}
