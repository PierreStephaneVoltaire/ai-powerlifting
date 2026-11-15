package views

import (
	"encoding/json"
	"math"
	"strconv"
	"strings"

	"powerlifting/profile/internal/value"
)

type Num struct {
	F   float64
	I   int64
	Int bool
}

func numOf(v any) (Num, bool) {
	var text string
	switch typed := v.(type) {
	case json.Number:
		text = string(typed)
	case value.Decimal:
		text = string(value.Sanitized(typed))
	case float64:
		return Num{F: typed}, true
	case int:
		return Num{F: float64(typed), I: int64(typed), Int: true}, true
	default:
		return Num{}, false
	}
	if !strings.ContainsAny(text, ".eE") {
		if i, err := strconv.ParseInt(text, 10, 64); err == nil {
			return Num{F: float64(i), I: i, Int: true}, true
		}
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return Num{}, false
	}
	return Num{F: f}, true
}

func positive(v any) (Num, bool) {
	n, ok := numOf(v)
	if !ok || n.F <= 0 {
		return Num{}, false
	}
	return Num{F: n.F}, true
}

func (n Num) Add(other Num) Num {
	if n.Int && other.Int {
		sum := n.I + other.I
		return Num{F: float64(sum), I: sum, Int: true}
	}
	return Num{F: n.F + other.F}
}

func (n Num) JSON() any {
	if n.Int {
		return json.Number(strconv.FormatInt(n.I, 10))
	}
	return json.Number(value.Float(n.F))
}

func roundEven(v float64) int { return int(math.RoundToEven(v)) }
