package pyval

import (
	"encoding/json"
	"math"
	"math/big"
	"sort"
	"strconv"
	"strings"
)

type Map = map[string]any

type List = []any

func IsDecimal(value any) bool {
	_, ok := value.(json.Number)
	return ok
}

func rat(number json.Number) (*big.Rat, bool) {
	return new(big.Rat).SetString(string(number))
}

func Float(value any) (float64, bool) {
	switch typed := value.(type) {
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case float64:
		return typed, true
	case bool:
		if typed {
			return 1, true
		}
		return 0, true
	case json.Number:
		r, ok := rat(typed)
		if !ok {
			return 0, false
		}
		f, _ := r.Float64()
		return f, true
	}
	return 0, false
}

func IsNumber(value any) bool {
	switch value.(type) {
	case int, int64, float64, json.Number:
		return true
	}
	return false
}

func Int(value any, fallback int) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case json.Number:
		r, ok := rat(typed)
		if !ok {
			return fallback
		}
		return int(new(big.Int).Quo(r.Num(), r.Denom()).Int64())
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err != nil {
			return fallback
		}
		return parsed
	}
	return fallback
}

func Truncate(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case int64:
		return int(typed), true
	case float64:
		if math.IsNaN(typed) || math.IsInf(typed, 0) {
			return 0, false
		}
		return int(typed), true
	case json.Number:
		r, ok := rat(typed)
		if !ok {
			return 0, false
		}
		return int(new(big.Int).Quo(r.Num(), r.Denom()).Int64()), true
	case bool:
		if typed {
			return 1, true
		}
		return 0, true
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		return parsed, err == nil
	}
	return 0, false
}

func Truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case int:
		return typed != 0
	case int64:
		return typed != 0
	case float64:
		return typed != 0
	case json.Number:
		f, _ := Float(typed)
		return f != 0
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	}
	return true
}

func String(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	}
	return Str(value)
}

func Str(value any) string {
	switch typed := value.(type) {
	case nil:
		return "None"
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case string:
		return typed
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case float64:
		return FloatRepr(typed)
	case json.Number:
		return DecimalStr(typed)
	case map[string]any:
		return dictRepr(typed)
	case []any:
		return listRepr(typed)
	}
	return ""
}

func Repr(value any) string {
	if text, ok := value.(string); ok {
		return quote(text)
	}
	return Str(value)
}

func quote(text string) string {
	quoteChar := "'"
	if strings.Contains(text, "'") && !strings.Contains(text, `"`) {
		quoteChar = `"`
	}
	escaped := strings.NewReplacer(`\`, `\\`, "\n", `\n`, "\r", `\r`, "\t", `\t`).Replace(text)
	if quoteChar == "'" {
		escaped = strings.ReplaceAll(escaped, "'", `\'`)
	}
	return quoteChar + escaped + quoteChar
}

func listRepr(values []any) string {
	parts := make([]string, len(values))
	for index, value := range values {
		parts[index] = Repr(value)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

func dictRepr(values map[string]any) string {
	keys := SortedKeys(values)
	parts := make([]string, len(keys))
	for index, key := range keys {
		parts[index] = quote(key) + ": " + Repr(values[key])
	}
	return "{" + strings.Join(parts, ", ") + "}"
}

func SortedKeys(values map[string]any) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func FloatRepr(value float64) string {
	if math.IsNaN(value) {
		return "nan"
	}
	if math.IsInf(value, 1) {
		return "inf"
	}
	if math.IsInf(value, -1) {
		return "-inf"
	}
	sign := ""
	if math.Signbit(value) {
		sign = "-"
		value = -value
	}
	if value == 0 {
		return sign + "0.0"
	}
	scientific := strconv.FormatFloat(value, 'e', -1, 64)
	mantissa, exponentText, _ := strings.Cut(scientific, "e")
	exponent, _ := strconv.Atoi(exponentText)
	digits := strings.Replace(mantissa, ".", "", 1)
	point := exponent + 1
	switch {
	case point > 16 || point < -3:
		text := digits[:1]
		if len(digits) > 1 {
			text += "." + digits[1:]
		}
		exponentSign := "+"
		if exponent < 0 {
			exponentSign = "-"
			exponent = -exponent
		}
		return sign + text + "e" + exponentSign + pad2(exponent)
	case point <= 0:
		return sign + "0." + strings.Repeat("0", -point) + digits
	case point >= len(digits):
		return sign + digits + strings.Repeat("0", point-len(digits)) + ".0"
	default:
		return sign + digits[:point] + "." + digits[point:]
	}
}

func pad2(value int) string {
	if value < 10 {
		return "0" + strconv.Itoa(value)
	}
	return strconv.Itoa(value)
}

func DecimalStr(number json.Number) string {
	text := string(number)
	negative := strings.HasPrefix(text, "-")
	text = strings.TrimPrefix(strings.TrimPrefix(text, "-"), "+")
	mantissa, exponentText, hasExponent := strings.Cut(strings.ToLower(text), "e")
	exponent := 0
	if hasExponent {
		exponent, _ = strconv.Atoi(exponentText)
	}
	integer, fraction, _ := strings.Cut(mantissa, ".")
	digits := strings.TrimLeft(integer+fraction, "0")
	exponent -= len(fraction)
	if digits == "" {
		digits = "0"
	}
	sign := ""
	if negative {
		sign = "-"
	}
	adjusted := exponent + len(digits) - 1
	if exponent <= 0 && adjusted >= -6 {
		switch {
		case exponent == 0:
			return sign + digits
		case -exponent >= len(digits):
			return sign + "0." + strings.Repeat("0", -exponent-len(digits)) + digits
		default:
			return sign + digits[:len(digits)+exponent] + "." + digits[len(digits)+exponent:]
		}
	}
	scientific := digits[:1]
	if len(digits) > 1 {
		scientific += "." + digits[1:]
	}
	if adjusted != 0 {
		exponentSign := "+"
		if adjusted < 0 {
			exponentSign = "-"
		}
		scientific += "E" + exponentSign + strconv.Itoa(int(math.Abs(float64(adjusted))))
	}
	return sign + scientific
}

func Normalize(number json.Number) json.Number {
	r, ok := rat(number)
	if !ok {
		return number
	}
	if r.IsInt() {
		return json.Number(r.Num().String())
	}
	text := r.FloatString(40)
	text = strings.TrimRight(text, "0")
	text = strings.TrimSuffix(text, ".")
	return json.Number(text)
}

func Coerce(value any) any {
	return convert(value, func(r *big.Rat) bool { return !r.IsInt() })
}

func Sanitize(value any) any {
	return Coerce(value)
}

func convert(value any, fractional func(*big.Rat) bool) any {
	switch typed := value.(type) {
	case json.Number:
		r, ok := rat(typed)
		if !ok {
			return typed
		}
		if fractional(r) {
			f, _ := r.Float64()
			return f
		}
		integer := new(big.Int).Quo(r.Num(), r.Denom())
		if integer.IsInt64() {
			return integer.Int64()
		}
		return json.Number(integer.String())
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[key] = convert(item, fractional)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, item := range typed {
			out[index] = convert(item, fractional)
		}
		return out
	}
	return value
}

func DeepCopy(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[key] = DeepCopy(item)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, item := range typed {
			out[index] = DeepCopy(item)
		}
		return out
	}
	return value
}

func CopyMap(value map[string]any) map[string]any {
	copied, _ := DeepCopy(value).(map[string]any)
	return copied
}

func AsMap(value any) (map[string]any, bool) {
	typed, ok := value.(map[string]any)
	return typed, ok
}

func AsList(value any) ([]any, bool) {
	typed, ok := value.([]any)
	return typed, ok
}

func Maps(value any) []map[string]any {
	list, _ := value.([]any)
	out := make([]map[string]any, 0, len(list))
	for _, item := range list {
		if typed, ok := item.(map[string]any); ok {
			out = append(out, typed)
		}
	}
	return out
}

func ToList(items []map[string]any) []any {
	out := make([]any, len(items))
	for index, item := range items {
		out[index] = item
	}
	return out
}

func Blank(value any) bool {
	if value == nil {
		return true
	}
	text, ok := value.(string)
	return ok && text == ""
}

func Equal(a, b any) bool {
	if fa, ok := Float(a); ok && IsNumber(a) && IsNumber(b) {
		fb, _ := Float(b)
		return fa == fb
	}
	switch typed := a.(type) {
	case string:
		other, ok := b.(string)
		return ok && typed == other
	case nil:
		return b == nil
	case bool:
		other, ok := b.(bool)
		return ok && typed == other
	}
	return false
}

func Decode(data []byte) (any, error) {
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	return Native(value), nil
}

func Native(value any) any {
	switch typed := value.(type) {
	case json.Number:
		text := string(typed)
		if !strings.ContainsAny(text, ".eE") {
			if parsed, err := strconv.ParseInt(text, 10, 64); err == nil {
				return parsed
			}
			return typed
		}
		parsed, err := strconv.ParseFloat(text, 64)
		if err != nil {
			return typed
		}
		return parsed
	case map[string]any:
		for key, item := range typed {
			typed[key] = Native(item)
		}
		return typed
	case []any:
		for index, item := range typed {
			typed[index] = Native(item)
		}
		return typed
	}
	return value
}

func Str2(value any) string {
	if !Truthy(value) {
		return ""
	}
	return Str(value)
}

func KeyOrder(raw []byte, path ...string) []string {
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	if !seek(decoder, path) {
		return nil
	}
	token, err := decoder.Token()
	if delim, ok := token.(json.Delim); err != nil || !ok || delim != '{' {
		return nil
	}
	var keys []string
	for decoder.More() {
		keyToken, err := decoder.Token()
		if err != nil {
			return keys
		}
		key, _ := keyToken.(string)
		keys = append(keys, key)
		var skipped json.RawMessage
		if err := decoder.Decode(&skipped); err != nil {
			return keys
		}
	}
	return keys
}

func seek(decoder *json.Decoder, path []string) bool {
	token, err := decoder.Token()
	if delim, ok := token.(json.Delim); err != nil || !ok || delim != '{' {
		return false
	}
	for _, name := range path {
		found := false
		for decoder.More() {
			keyToken, err := decoder.Token()
			if err != nil {
				return false
			}
			if key, _ := keyToken.(string); key == name {
				found = true
				break
			}
			var skipped json.RawMessage
			if err := decoder.Decode(&skipped); err != nil {
				return false
			}
		}
		if !found {
			return false
		}
		if name != path[len(path)-1] {
			token, err := decoder.Token()
			if delim, ok := token.(json.Delim); err != nil || !ok || delim != '{' {
				return false
			}
		} else {
			return true
		}
	}
	return true
}
