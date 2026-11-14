package pyval

import (
	"encoding/json"
	"math"
	"strconv"
	"strings"

	"powerlifting/competition/internal/pyjson"
)

func Truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case json.Number:
		parsed, err := strconv.ParseFloat(typed.String(), 64)
		return err != nil || parsed != 0
	case float64:
		return typed != 0
	case int:
		return typed != 0
	case int64:
		return typed != 0
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	}
	return true
}

func Float(value any) (float64, bool) {
	switch typed := value.(type) {
	case json.Number:
		parsed, err := strconv.ParseFloat(typed.String(), 64)
		return parsed, err == nil
	case float64:
		return typed, true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	}
	return 0, false
}

func IsInteger(value any) bool {
	switch typed := value.(type) {
	case json.Number:
		return !strings.ContainsAny(typed.String(), ".eE")
	case int, int64:
		return true
	}
	return false
}

func Number(value float64) any {
	if value == math.Trunc(value) && math.Abs(value) < 1e15 {
		return json.Number(strconv.FormatInt(int64(value), 10))
	}
	return value
}

func Str(value any) string {
	switch typed := value.(type) {
	case nil:
		return "None"
	case string:
		return typed
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case json.Number:
		if IsInteger(typed) {
			return typed.String()
		}
		parsed, _ := strconv.ParseFloat(typed.String(), 64)
		return pyjson.Float(parsed)
	case float64:
		return pyjson.Float(typed)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	}
	encoded, _ := pyjson.Encode(value)
	return string(encoded)
}

func Or(values ...any) any {
	for _, value := range values {
		if Truthy(value) {
			return value
		}
	}
	if len(values) == 0 {
		return nil
	}
	return values[len(values)-1]
}

func Equal(a, b any) bool {
	left, leftNumber := Float(a)
	right, rightNumber := Float(b)
	if leftNumber && rightNumber {
		return left == right
	}
	if leftNumber != rightNumber {
		return false
	}
	switch typed := a.(type) {
	case string:
		other, ok := b.(string)
		return ok && typed == other
	case bool:
		other, ok := b.(bool)
		return ok && typed == other
	case nil:
		return b == nil
	}
	return false
}

func Copy(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[key] = Copy(item)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, item := range typed {
			out[index] = Copy(item)
		}
		return out
	}
	return value
}
