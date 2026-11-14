package store

import (
	"encoding/json"
	"sort"
	"strconv"
	"strings"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func ToAttr(value any) types.AttributeValue {
	switch typed := value.(type) {
	case nil:
		return &types.AttributeValueMemberNULL{Value: true}
	case bool:
		return &types.AttributeValueMemberBOOL{Value: typed}
	case string:
		return &types.AttributeValueMemberS{Value: typed}
	case json.Number:
		return &types.AttributeValueMemberN{Value: numberText(typed.String())}
	case float64:
		return &types.AttributeValueMemberN{Value: strconv.FormatFloat(typed, 'f', -1, 64)}
	case int:
		return &types.AttributeValueMemberN{Value: strconv.Itoa(typed)}
	case int64:
		return &types.AttributeValueMemberN{Value: strconv.FormatInt(typed, 10)}
	case []any:
		list := make([]types.AttributeValue, len(typed))
		for index, item := range typed {
			list[index] = ToAttr(item)
		}
		return &types.AttributeValueMemberL{Value: list}
	case map[string]any:
		return &types.AttributeValueMemberM{Value: ToItem(typed)}
	}
	return &types.AttributeValueMemberNULL{Value: true}
}

func numberText(text string) string {
	if !strings.ContainsAny(text, ".eE") {
		return text
	}
	parsed, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return text
	}
	return strconv.FormatFloat(parsed, 'f', -1, 64)
}

func ToItem(item map[string]any) map[string]types.AttributeValue {
	out := make(map[string]types.AttributeValue, len(item))
	for key, value := range item {
		out[key] = ToAttr(value)
	}
	return out
}

func FromAttr(value types.AttributeValue) any {
	switch typed := value.(type) {
	case *types.AttributeValueMemberNULL:
		return nil
	case *types.AttributeValueMemberBOOL:
		return typed.Value
	case *types.AttributeValueMemberS:
		return typed.Value
	case *types.AttributeValueMemberN:
		parsed, _ := strconv.ParseFloat(typed.Value, 64)
		return parsed
	case *types.AttributeValueMemberL:
		list := make([]any, len(typed.Value))
		for index, item := range typed.Value {
			list[index] = FromAttr(item)
		}
		return list
	case *types.AttributeValueMemberM:
		return FromItem(typed.Value)
	case *types.AttributeValueMemberSS:
		list := make([]any, len(typed.Value))
		for index, item := range typed.Value {
			list[index] = item
		}
		sort.Slice(list, func(i, j int) bool { return list[i].(string) < list[j].(string) })
		return list
	case *types.AttributeValueMemberNS:
		list := make([]any, len(typed.Value))
		for index, item := range typed.Value {
			list[index], _ = strconv.ParseFloat(item, 64)
		}
		return list
	}
	return nil
}

func FromItem(item map[string]types.AttributeValue) map[string]any {
	out := make(map[string]any, len(item))
	for key, value := range item {
		out[key] = FromAttr(value)
	}
	return out
}
