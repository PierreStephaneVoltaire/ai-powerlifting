package pyjson

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
)

func Decode(data []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, fmt.Errorf("unexpected trailing data")
	}
	return value, nil
}

func Encode(value any) ([]byte, error) {
	var out bytes.Buffer
	if err := write(&out, value); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func write(out *bytes.Buffer, value any) error {
	switch typed := value.(type) {
	case nil:
		out.WriteString("null")
	case bool:
		out.WriteString(strconv.FormatBool(typed))
	case string:
		writeString(out, typed)
	case json.Number:
		return writeNumber(out, typed.String())
	case float64:
		return writeFloat(out, typed)
	case float32:
		return writeFloat(out, float64(typed))
	case int:
		out.WriteString(strconv.Itoa(typed))
	case int32:
		out.WriteString(strconv.FormatInt(int64(typed), 10))
	case int64:
		out.WriteString(strconv.FormatInt(typed, 10))
	case uint64:
		out.WriteString(strconv.FormatUint(typed, 10))
	case map[string]any:
		return writeObject(out, typed)
	case []any:
		out.WriteByte('[')
		for index, item := range typed {
			if index > 0 {
				out.WriteString(", ")
			}
			if err := write(out, item); err != nil {
				return err
			}
		}
		out.WriteByte(']')
	default:
		raw, err := json.Marshal(typed)
		if err != nil {
			return err
		}
		generic, err := Decode(raw)
		if err != nil {
			return err
		}
		return write(out, generic)
	}
	return nil
}

func writeObject(out *bytes.Buffer, object map[string]any) error {
	keys := make([]string, 0, len(object))
	for key := range object {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	out.WriteByte('{')
	for index, key := range keys {
		if index > 0 {
			out.WriteString(", ")
		}
		writeString(out, key)
		out.WriteString(": ")
		if err := write(out, object[key]); err != nil {
			return err
		}
	}
	out.WriteByte('}')
	return nil
}

func writeString(out *bytes.Buffer, text string) {
	out.WriteByte('"')
	for _, r := range text {
		switch {
		case r == '"':
			out.WriteString(`\"`)
		case r == '\\':
			out.WriteString(`\\`)
		case r == '\n':
			out.WriteString(`\n`)
		case r == '\r':
			out.WriteString(`\r`)
		case r == '\t':
			out.WriteString(`\t`)
		case r == '\b':
			out.WriteString(`\b`)
		case r == '\f':
			out.WriteString(`\f`)
		case r >= 0x20 && r <= 0x7e:
			out.WriteRune(r)
		case r > 0xffff:
			high, low := utf16.EncodeRune(r)
			fmt.Fprintf(out, `\u%04x\u%04x`, high, low)
		default:
			fmt.Fprintf(out, `\u%04x`, r)
		}
	}
	out.WriteByte('"')
}

func writeNumber(out *bytes.Buffer, text string) error {
	if !strings.ContainsAny(text, ".eE") {
		out.WriteString(normalizeInteger(text))
		return nil
	}
	parsed, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return err
	}
	return writeFloat(out, parsed)
}

func normalizeInteger(text string) string {
	negative := strings.HasPrefix(text, "-")
	digits := strings.TrimLeft(strings.TrimPrefix(text, "-"), "0")
	if digits == "" {
		return "0"
	}
	if negative {
		return "-" + digits
	}
	return digits
}

func writeFloat(out *bytes.Buffer, value float64) error {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Errorf("non-finite number")
	}
	out.WriteString(Float(value))
	return nil
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
		return fmt.Sprintf("%s%se%s%02d", sign, text, exponentSign, exponent)
	case point <= 0:
		return sign + "0." + strings.Repeat("0", -point) + digits
	case point >= len(digits):
		return sign + digits + strings.Repeat("0", point-len(digits)) + ".0"
	default:
		return sign + digits[:point] + "." + digits[point:]
	}
}
