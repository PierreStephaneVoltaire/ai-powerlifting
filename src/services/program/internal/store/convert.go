package store

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"powerlifting/program/internal/pyval"
)

type StringSet []string

type NumberSet []json.Number

func FromAttr(value types.AttributeValue) any {
	switch typed := value.(type) {
	case *types.AttributeValueMemberS:
		return typed.Value
	case *types.AttributeValueMemberN:
		return json.Number(typed.Value)
	case *types.AttributeValueMemberBOOL:
		return typed.Value
	case *types.AttributeValueMemberNULL:
		return nil
	case *types.AttributeValueMemberM:
		return FromAttrMap(typed.Value)
	case *types.AttributeValueMemberL:
		out := make([]any, len(typed.Value))
		for index, item := range typed.Value {
			out[index] = FromAttr(item)
		}
		return out
	case *types.AttributeValueMemberSS:
		return StringSet(typed.Value)
	case *types.AttributeValueMemberNS:
		set := make(NumberSet, len(typed.Value))
		for index, item := range typed.Value {
			set[index] = json.Number(item)
		}
		return set
	case *types.AttributeValueMemberB:
		return typed.Value
	}
	return nil
}

func FromAttrMap(values map[string]types.AttributeValue) map[string]any {
	out := make(map[string]any, len(values))
	for key, value := range values {
		out[key] = FromAttr(value)
	}
	return out
}

func ToAttr(value any) (types.AttributeValue, error) {
	switch typed := value.(type) {
	case nil:
		return &types.AttributeValueMemberNULL{Value: true}, nil
	case string:
		return &types.AttributeValueMemberS{Value: typed}, nil
	case bool:
		return &types.AttributeValueMemberBOOL{Value: typed}, nil
	case int:
		return &types.AttributeValueMemberN{Value: strconv.Itoa(typed)}, nil
	case int64:
		return &types.AttributeValueMemberN{Value: strconv.FormatInt(typed, 10)}, nil
	case json.Number:
		return &types.AttributeValueMemberN{Value: string(typed)}, nil
	case float64:
		if math.IsNaN(typed) || math.IsInf(typed, 0) {
			return nil, fmt.Errorf("non-finite number")
		}
		return &types.AttributeValueMemberN{Value: floatNumber(typed)}, nil
	case []byte:
		return &types.AttributeValueMemberB{Value: typed}, nil
	case StringSet:
		return &types.AttributeValueMemberSS{Value: []string(typed)}, nil
	case NumberSet:
		values := make([]string, len(typed))
		for index, item := range typed {
			values[index] = string(item)
		}
		return &types.AttributeValueMemberNS{Value: values}, nil
	case map[string]any:
		converted, err := ToAttrMap(typed)
		if err != nil {
			return nil, err
		}
		return &types.AttributeValueMemberM{Value: converted}, nil
	case []any:
		list := make([]types.AttributeValue, len(typed))
		for index, item := range typed {
			converted, err := ToAttr(item)
			if err != nil {
				return nil, err
			}
			list[index] = converted
		}
		return &types.AttributeValueMemberL{Value: list}, nil
	}
	return nil, fmt.Errorf("unsupported value type %T", value)
}

func floatNumber(value float64) string {
	repr := pyval.FloatRepr(value)
	if len(repr) > 2 && repr[len(repr)-2:] == ".0" {
		return repr[:len(repr)-2]
	}
	return repr
}

func ToAttrMap(values map[string]any) (map[string]types.AttributeValue, error) {
	out := make(map[string]types.AttributeValue, len(values))
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		converted, err := ToAttr(values[key])
		if err != nil {
			return nil, fmt.Errorf("%s: %w", key, err)
		}
		out[key] = converted
	}
	return out, nil
}
