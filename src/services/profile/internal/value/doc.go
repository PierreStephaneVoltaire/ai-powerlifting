package value

import (
	"bytes"
	"encoding/json"
	"io"
	"sort"
	"strconv"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Item = map[string]any

type StringSet []string

func Decode(raw []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var out any
	if err := decoder.Decode(&out); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, io.ErrUnexpectedEOF
	}
	return out, nil
}

func Copy(v any) any {
	switch typed := v.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = Copy(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = Copy(child)
		}
		return out
	}
	return v
}

func CopyItem(item Item) Item { return Copy(item).(map[string]any) }

func Sanitize(v any) any {
	switch typed := v.(type) {
	case Decimal:
		return Sanitized(typed)
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = Sanitize(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = Sanitize(child)
		}
		return out
	}
	return v
}

func Render(v any) any {
	switch typed := v.(type) {
	case Decimal:
		return Sanitized(typed)
	case json.Number:
		return Canonical(typed)
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, child := range typed {
			out[key] = Render(child)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, child := range typed {
			out[i] = Render(child)
		}
		return out
	}
	return v
}

func Truthy(v any) bool {
	switch typed := v.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case Decimal:
		return Sanitized(typed) != "0"
	case json.Number:
		text := Canonical(typed)
		return text != "0" && text != "0.0" && text != "-0.0"
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	}
	return true
}

func Or(v any, fallback any) any {
	if Truthy(v) {
		return v
	}
	return fallback
}

func Str(v any) string {
	switch typed := v.(type) {
	case nil:
		return "None"
	case string:
		return typed
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case Decimal:
		return string(Sanitized(typed))
	case json.Number:
		return string(Canonical(typed))
	}
	encoded, _ := json.Marshal(Render(v))
	return string(encoded)
}

func Map(v any) (map[string]any, bool) {
	typed, ok := v.(map[string]any)
	return typed, ok
}

func ToAV(item Item) map[string]types.AttributeValue {
	out := make(map[string]types.AttributeValue, len(item))
	for key, v := range item {
		out[key] = toAttribute(v)
	}
	return out
}

func toAttribute(v any) types.AttributeValue {
	switch typed := v.(type) {
	case nil:
		return &types.AttributeValueMemberNULL{Value: true}
	case bool:
		return &types.AttributeValueMemberBOOL{Value: typed}
	case string:
		return &types.AttributeValueMemberS{Value: typed}
	case Decimal:
		return &types.AttributeValueMemberN{Value: string(typed)}
	case json.Number:
		return &types.AttributeValueMemberN{Value: string(Stored(typed))}
	case int:
		return &types.AttributeValueMemberN{Value: strconv.Itoa(typed)}
	case int64:
		return &types.AttributeValueMemberN{Value: strconv.FormatInt(typed, 10)}
	case float64:
		return &types.AttributeValueMemberN{Value: string(Stored(json.Number(Float(typed))))}
	case StringSet:
		return &types.AttributeValueMemberSS{Value: append([]string(nil), typed...)}
	case []string:
		list := make([]types.AttributeValue, len(typed))
		for i, child := range typed {
			list[i] = &types.AttributeValueMemberS{Value: child}
		}
		return &types.AttributeValueMemberL{Value: list}
	case []any:
		list := make([]types.AttributeValue, len(typed))
		for i, child := range typed {
			list[i] = toAttribute(child)
		}
		return &types.AttributeValueMemberL{Value: list}
	case map[string]any:
		return &types.AttributeValueMemberM{Value: ToAV(typed)}
	}
	return &types.AttributeValueMemberS{Value: Str(v)}
}

func FromAV(av map[string]types.AttributeValue) Item {
	out := make(Item, len(av))
	for key, v := range av {
		out[key] = fromAttribute(v)
	}
	return out
}

func fromAttribute(v types.AttributeValue) any {
	switch typed := v.(type) {
	case *types.AttributeValueMemberS:
		return typed.Value
	case *types.AttributeValueMemberN:
		return Decimal(typed.Value)
	case *types.AttributeValueMemberBOOL:
		return typed.Value
	case *types.AttributeValueMemberNULL:
		return nil
	case *types.AttributeValueMemberL:
		list := make([]any, len(typed.Value))
		for i, child := range typed.Value {
			list[i] = fromAttribute(child)
		}
		return list
	case *types.AttributeValueMemberM:
		return FromAV(typed.Value)
	case *types.AttributeValueMemberSS:
		values := append([]string(nil), typed.Value...)
		sort.Strings(values)
		list := make([]any, len(values))
		for i, s := range values {
			list[i] = s
		}
		return list
	case *types.AttributeValueMemberNS:
		list := make([]any, len(typed.Value))
		for i, s := range typed.Value {
			list[i] = Decimal(s)
		}
		return list
	}
	return nil
}
