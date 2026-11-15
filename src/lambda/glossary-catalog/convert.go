package main

import (
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func convertImage(in map[string]events.DynamoDBAttributeValue) map[string]types.AttributeValue {
	out := make(map[string]types.AttributeValue, len(in))
	for k, v := range in {
		out[k] = convertValue(v)
	}
	return out
}

func convertValue(v events.DynamoDBAttributeValue) types.AttributeValue {
	switch v.DataType() {
	case events.DataTypeString:
		return &types.AttributeValueMemberS{Value: v.String()}
	case events.DataTypeNumber:
		return &types.AttributeValueMemberN{Value: v.Number()}
	case events.DataTypeBoolean:
		return &types.AttributeValueMemberBOOL{Value: v.Boolean()}
	case events.DataTypeBinary:
		return &types.AttributeValueMemberB{Value: v.Binary()}
	case events.DataTypeStringSet:
		return &types.AttributeValueMemberSS{Value: v.StringSet()}
	case events.DataTypeNumberSet:
		return &types.AttributeValueMemberNS{Value: v.NumberSet()}
	case events.DataTypeBinarySet:
		return &types.AttributeValueMemberBS{Value: v.BinarySet()}
	case events.DataTypeList:
		list := make([]types.AttributeValue, 0, len(v.List()))
		for _, e := range v.List() {
			list = append(list, convertValue(e))
		}
		return &types.AttributeValueMemberL{Value: list}
	case events.DataTypeMap:
		return &types.AttributeValueMemberM{Value: convertImage(v.Map())}
	default:
		return &types.AttributeValueMemberNULL{Value: true}
	}
}
