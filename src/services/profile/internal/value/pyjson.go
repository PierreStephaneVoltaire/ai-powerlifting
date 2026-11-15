package value

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"unicode/utf16"
)

func Dump(v any) string {
	var out strings.Builder
	dump(&out, v, ",", ":")
	return out.String()
}

func DumpSpaced(v any) string {
	var out strings.Builder
	dump(&out, v, ", ", ": ")
	return out.String()
}

func dump(out *strings.Builder, v any, itemSep, keySep string) {
	switch typed := v.(type) {
	case nil:
		out.WriteString("null")
	case bool:
		if typed {
			out.WriteString("true")
		} else {
			out.WriteString("false")
		}
	case string:
		dumpString(out, typed)
	case Decimal:
		out.WriteString(string(Sanitized(typed)))
	case json.Number:
		out.WriteString(string(Canonical(typed)))
	case int:
		fmt.Fprintf(out, "%d", typed)
	case float64:
		out.WriteString(Float(typed))
	case []string:
		out.WriteByte('[')
		for i, item := range typed {
			if i > 0 {
				out.WriteString(itemSep)
			}
			dumpString(out, item)
		}
		out.WriteByte(']')
	case []any:
		out.WriteByte('[')
		for i, item := range typed {
			if i > 0 {
				out.WriteString(itemSep)
			}
			dump(out, item, itemSep, keySep)
		}
		out.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(typed))
		for key := range typed {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		out.WriteByte('{')
		for i, key := range keys {
			if i > 0 {
				out.WriteString(itemSep)
			}
			dumpString(out, key)
			out.WriteString(keySep)
			dump(out, typed[key], itemSep, keySep)
		}
		out.WriteByte('}')
	default:
		dumpString(out, Str(v))
	}
}

func dumpString(out *strings.Builder, text string) {
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
		case r < 0x20:
			fmt.Fprintf(out, `\u%04x`, r)
		case r <= 0x7f:
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
