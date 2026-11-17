package store

import (
	"context"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"strings"
)

type Store struct {
	DB                 *dynamodb.Client
	Table, MasterTable string
}

func (s Store) Get(ctx context.Context, pk string) (map[string]any, error) {
	r, e := s.DB.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(s.Table), Key: ToItem(map[string]any{"pk": pk, "sk": "federations#v1"})})
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
func (s Store) List(ctx context.Context) ([]map[string]any, error) {
	out := []map[string]any{}
	var start map[string]types.AttributeValue
	for {
		r, e := s.DB.Scan(ctx, &dynamodb.ScanInput{TableName: aws.String(s.MasterTable), ExclusiveStartKey: start})
		if e != nil {
			return nil, e
		}
		for _, item := range r.Items {
			out = append(out, FromItem(item))
		}
		start = r.LastEvaluatedKey
		if len(start) == 0 {
			return out, nil
		}
	}
}
func (s Store) Update(ctx context.Context, id string, fields map[string]any) error {
	names := map[string]string{}
	values := map[string]types.AttributeValue{}
	sets := []string{}
	i := 0
	for k, v := range fields {
		n, p := fmt.Sprintf("#n%d", i), fmt.Sprintf(":v%d", i)
		names[n] = k
		values[p] = ToAttr(v)
		sets = append(sets, n+" = "+p)
		i++
	}
	_, e := s.DB.UpdateItem(ctx, &dynamodb.UpdateItemInput{TableName: aws.String(s.MasterTable), Key: ToItem(map[string]any{"pk": "FED#" + strings.TrimPrefix(id, "FED#")}), UpdateExpression: aws.String("SET " + strings.Join(sets, ", ")), ExpressionAttributeNames: names, ExpressionAttributeValues: values})
	return e
}
