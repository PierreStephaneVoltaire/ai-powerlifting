package main

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"golang.org/x/text/cases"
)

const (
	athletePrefix  = "ATHLETE#"
	exercisePrefix = "EXERCISE#"
	catalogPK      = "CATALOG"
	catalogNamePK  = "CATALOG_NAME"
	notExists      = "attribute_not_exists(pk)"
)

var definitionFields = []string{
	"category",
	"equipment",
	"primary_muscles",
	"secondary_muscles",
	"tertiary_muscles",
	"description",
	"how_to_perform",
	"why_do_it",
	"video_url",
	"lift_transfer",
	"lift_transfer_source",
	"lift_transfer_reasoning",
	"created_by_person",
}

type transactor interface {
	TransactWriteItems(ctx context.Context, in *dynamodb.TransactWriteItemsInput, opts ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}

type catalog struct {
	client transactor
	table  string
	now    func() time.Time
}

func nameKey(name string) string {
	return cases.Fold().String(strings.Join(strings.Fields(name), " "))
}

func (c *catalog) ensure(ctx context.Context, image map[string]types.AttributeValue) error {
	pk, ok := stringAttr(image, "pk")
	if !ok || !strings.HasPrefix(pk, athletePrefix) {
		return nil
	}
	if custom, ok := image["custom"].(*types.AttributeValueMemberBOOL); !ok || !custom.Value {
		return nil
	}
	sk, ok := stringAttr(image, "sk")
	if !ok || !strings.HasPrefix(sk, exercisePrefix) {
		return nil
	}
	name, _ := stringAttr(image, "name")
	key := nameKey(name)
	if key == "" {
		return nil
	}
	id := strings.TrimPrefix(sk, exercisePrefix)
	now := c.now().UTC().Format(time.RFC3339)

	item := map[string]types.AttributeValue{
		"pk":              &types.AttributeValueMemberS{Value: catalogPK},
		"sk":              &types.AttributeValueMemberS{Value: sk},
		"id":              &types.AttributeValueMemberS{Value: id},
		"name":            &types.AttributeValueMemberS{Value: name},
		"name_key":        &types.AttributeValueMemberS{Value: key},
		"generic_status":  &types.AttributeValueMemberS{Value: "pending"},
		"generic_pending": &types.AttributeValueMemberS{Value: "1"},
		"created_by":      &types.AttributeValueMemberS{Value: strings.TrimPrefix(pk, athletePrefix)},
		"created_at":      &types.AttributeValueMemberS{Value: now},
		"updated_at":      &types.AttributeValueMemberS{Value: now},
	}
	for _, field := range definitionFields {
		if v, ok := image[field]; ok {
			if _, null := v.(*types.AttributeValueMemberNULL); !null {
				item[field] = v
			}
		}
	}
	nameItem := map[string]types.AttributeValue{
		"pk": &types.AttributeValueMemberS{Value: catalogNamePK},
		"sk": &types.AttributeValueMemberS{Value: key},
		"id": &types.AttributeValueMemberS{Value: id},
	}

	cond := notExists
	_, err := c.client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: []types.TransactWriteItem{
			{Put: &types.Put{TableName: &c.table, Item: item, ConditionExpression: &cond}},
			{Put: &types.Put{TableName: &c.table, Item: nameItem, ConditionExpression: &cond}},
		},
	})
	if isConflict(err) {
		return nil
	}
	return err
}

func isConflict(err error) bool {
	var canceled *types.TransactionCanceledException
	if !errors.As(err, &canceled) {
		return false
	}
	for _, reason := range canceled.CancellationReasons {
		if reason.Code != nil && *reason.Code == "ConditionalCheckFailed" {
			return true
		}
	}
	return false
}

func stringAttr(image map[string]types.AttributeValue, key string) (string, bool) {
	v, ok := image[key].(*types.AttributeValueMemberS)
	if !ok {
		return "", false
	}
	return v.Value, true
}
