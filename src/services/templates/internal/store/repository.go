package store

import (
	"context"
	"errors"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"powerlifting/templates/internal/library"
)

type Client interface {
	GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
	Query(context.Context, *dynamodb.QueryInput, ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
	TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
}
type Repository struct {
	Client        Client
	Table         string
	HealthTable   string
	GlossaryTable string
	SessionsTable string
}

func (d Repository) VerifyClaim(ctx context.Context, claim library.ImportClaim) (bool, error) {
	out, err := d.Client.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(d.HealthTable), Key: key(claim.Athlete, "import#pending#"+claim.ImportID), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return false, err
	}
	status, _ := out.Item["status"].(*types.AttributeValueMemberS)
	id, _ := out.Item["apply_claim_id"].(*types.AttributeValueMemberS)
	return status != nil && status.Value == "applying" && id != nil && id.Value == claim.ClaimID, nil
}

func key(pk, sk string) map[string]types.AttributeValue {
	return map[string]types.AttributeValue{"pk": &types.AttributeValueMemberS{Value: pk}, "sk": &types.AttributeValueMemberS{Value: sk}}
}
func (d Repository) Get(ctx context.Context, pk, sk string) (map[string]any, error) {
	out, err := d.Client.GetItem(ctx, &dynamodb.GetItemInput{TableName: aws.String(d.Table), Key: key(pk, sk), ConsistentRead: aws.Bool(true)})
	if err != nil {
		return nil, err
	}
	if len(out.Item) == 0 {
		return nil, nil
	}
	var item map[string]any
	if err = attributevalue.UnmarshalMap(out.Item, &item); err != nil {
		return nil, err
	}
	return item, nil
}
func (d Repository) Commit(ctx context.Context, item map[string]any, remove bool, claim *library.ImportClaim, index map[string]any, revision string) error {
	rawIndex, err := attributevalue.MarshalMap(index)
	if err != nil {
		return err
	}
	putIndex := &types.Put{TableName: aws.String(d.Table), Item: rawIndex, ExpressionAttributeNames: map[string]string{"#revision": "index_revision"}}
	if revision == "" {
		putIndex.ConditionExpression = aws.String("attribute_not_exists(#revision)")
	} else {
		putIndex.ConditionExpression = aws.String("#revision = :revision")
		putIndex.ExpressionAttributeValues = map[string]types.AttributeValue{":revision": &types.AttributeValueMemberS{Value: revision}}
	}
	writes := []types.TransactWriteItem{{Put: putIndex}}
	if remove {
		pk, _ := item["pk"].(string)
		sk, _ := item["sk"].(string)
		writes = append(writes, types.TransactWriteItem{Delete: &types.Delete{TableName: aws.String(d.Table), Key: key(pk, sk)}})
	} else {
		rawItem, err := attributevalue.MarshalMap(item)
		if err != nil {
			return err
		}
		put := &types.Put{TableName: aws.String(d.Table), Item: rawItem}
		if claim != nil {
			put.ConditionExpression = aws.String("attribute_not_exists(pk)")
		}
		writes = append(writes, types.TransactWriteItem{Put: put})
	}
	if claim != nil {
		writes = append(writes, types.TransactWriteItem{ConditionCheck: &types.ConditionCheck{
			TableName: aws.String(d.HealthTable), Key: key(claim.Athlete, "import#pending#"+claim.ImportID),
			ConditionExpression:       aws.String("#status = :applying AND apply_claim_id = :claim"),
			ExpressionAttributeNames:  map[string]string{"#status": "status"},
			ExpressionAttributeValues: map[string]types.AttributeValue{":applying": &types.AttributeValueMemberS{Value: "applying"}, ":claim": &types.AttributeValueMemberS{Value: claim.ClaimID}},
		}})
	}
	_, err = d.Client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{TransactItems: writes})
	var canceled *types.TransactionCanceledException
	if errors.As(err, &canceled) && len(canceled.CancellationReasons) > 0 && aws.ToString(canceled.CancellationReasons[0].Code) == "ConditionalCheckFailed" {
		return library.ErrConflict
	}
	return err
}
