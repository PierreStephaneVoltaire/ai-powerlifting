package value

import (
	"encoding/json"
	"math"
	"math/big"
	"strconv"
	"strings"
)

type Decimal string

func (d Decimal) MarshalJSON() ([]byte, error) {
	return []byte(Sanitized(d).String()), nil
}

func Int(n int) json.Number { return json.Number(strconv.Itoa(n)) }

func isFloat(text string) bool { return strings.ContainsAny(text, ".eE") }

func Sanitized(d Decimal) json.Number {
	rat, ok := new(big.Rat).SetString(string(d))
	if !ok {
		return json.Number(d)
	}
	if rat.IsInt() {
		return json.Number(rat.Num().String())
	}
	f, _ := rat.Float64()
	return json.Number(Float(f))
}

func Canonical(n json.Number) json.Number {
	text := string(n)
	if !isFloat(text) {
		if parsed, ok := new(big.Int).SetString(text, 10); ok {
			return json.Number(parsed.String())
		}
		return n
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
		return n
	}
	return json.Number(Float(f))
}

func Float(value float64) string {
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

func pad2(n int) string {
	if n < 10 {
		return "0" + strconv.Itoa(n)
	}
	return strconv.Itoa(n)
}

func Stored(n json.Number) Decimal {
	text := string(n)
	if !isFloat(text) {
		return Decimal(text)
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
		return Decimal(text)
	}
	repr := Float(f)
	mantissa, exponent, scientific := strings.Cut(repr, "e")
	if !scientific {
		return Decimal(repr)
	}
	exp, _ := strconv.Atoi(exponent)
	sign := "+"
	if exp < 0 {
		sign = "-"
		exp = -exp
	}
	return Decimal(mantissa + "E" + sign + strconv.Itoa(exp))
}

func IntOf(v any, fallback int) int {
	switch typed := v.(type) {
	case Decimal:
		rat, ok := new(big.Rat).SetString(string(typed))
		if !ok {
			return fallback
		}
		return clamp(new(big.Int).Quo(rat.Num(), rat.Denom()))
	case json.Number:
		if isFloat(string(typed)) {
			return fallback
		}
		parsed, ok := new(big.Int).SetString(string(typed), 10)
		if !ok {
			return fallback
		}
		return clamp(parsed)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err != nil {
			return fallback
		}
		return parsed
	}
	return fallback
}

func clamp(n *big.Int) int {
	if !n.IsInt64() {
		if n.Sign() < 0 {
			return math.MinInt64
		}
		return math.MaxInt64
	}
	return int(n.Int64())
}

func Rat(v any, fallback int64) *big.Rat {
	switch typed := v.(type) {
	case Decimal:
		if rat, ok := new(big.Rat).SetString(string(typed)); ok {
			return rat
		}
	case json.Number:
		if rat, ok := new(big.Rat).SetString(string(typed)); ok {
			return rat
		}
	}
	return new(big.Rat).SetInt64(fallback)
}
