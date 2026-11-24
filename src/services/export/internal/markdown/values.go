package markdown

import (
	"encoding/json"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"powerlifting/export/internal/values"
)

type M = map[string]any

func get(m M, key string) any { return m[key] }

func getd(m M, key string, fallback any) any {
	if value, present := m[key]; present {
		return value
	}
	return fallback
}

func blank(value any) bool { return values.Blank(value) }

func truthy(value any) bool { return values.Truthy(value) }

func str(value any) string { return values.Str(value) }

func num(value any) any {
	switch typed := value.(type) {
	case json.Number:
		return values.Coerce(typed)
	case map[string]any, []any:
		return values.Str(typed)
	}
	return value
}

func tcell(value any) string {
	if value == nil || blank(value) {
		return ""
	}
	text := str(num(value))
	text = strings.ReplaceAll(text, "|", `\|`)
	text = strings.ReplaceAll(text, "\n", " ")
	return strings.ReplaceAll(text, "\r", "")
}

func txt(value any) string {
	if value == nil || blank(value) {
		return ""
	}
	return strings.TrimSpace(str(num(value)))
}

func firstLine(value any) string {
	text := txt(value)
	if text == "" {
		return ""
	}
	first, _, _ := strings.Cut(text, "\n")
	return strings.TrimSpace(first)
}

func firstNonBlank(values ...any) any {
	for _, value := range values {
		if !blank(value) {
			return value
		}
	}
	return ""
}

func floatOf(value any) (float64, bool) {
	if text, ok := value.(string); ok {
		parsed, err := strconv.ParseFloat(strings.TrimSpace(text), 64)
		return parsed, err == nil
	}
	if value == nil {
		return 0, false
	}
	return values.Float(value)
}

func title(text string) string {
	var builder strings.Builder
	previousLetter := false
	for _, r := range text {
		if unicode.IsLetter(r) {
			if previousLetter {
				builder.WriteRune(unicode.ToLower(r))
			} else {
				builder.WriteRune(unicode.ToUpper(r))
			}
			previousLetter = true
		} else {
			builder.WriteRune(r)
			previousLetter = false
		}
	}
	return builder.String()
}

func maps(value any) []M {
	list, _ := value.([]any)
	out := make([]M, 0, len(list))
	for _, item := range list {
		out = append(out, copyOf(item))
	}
	return out
}

func copyOf(item any) M {
	typed, _ := values.DeepCopy(item).(map[string]any)
	return typed
}

func asMap(value any) M {
	typed, _ := value.(map[string]any)
	return typed
}

func table(headers []string, rows [][]any) string {
	if len(rows) == 0 {
		return ""
	}
	var builder strings.Builder
	builder.WriteString("| " + strings.Join(headers, " | ") + " |\n")
	separators := make([]string, len(headers))
	for index := range separators {
		separators[index] = "---"
	}
	builder.WriteString("| " + strings.Join(separators, " | ") + " |")
	for _, row := range rows {
		cells := make([]string, 0, len(headers))
		for _, value := range row {
			cells = append(cells, tcell(value))
		}
		for len(cells) < len(headers) {
			cells = append(cells, "")
		}
		builder.WriteString("\n| " + strings.Join(cells[:len(headers)], " | ") + " |")
	}
	return builder.String()
}

func sortedStable[T any](items []T, less func(a, b T) bool) []T {
	out := append([]T(nil), items...)
	sort.SliceStable(out, func(i, j int) bool { return less(out[i], out[j]) })
	return out
}

func intOf(value any) (int, bool) {
	if value == nil {
		return 0, false
	}
	if text, ok := value.(string); ok {
		parsed, err := strconv.Atoi(strings.TrimSpace(text))
		return parsed, err == nil
	}
	return values.Truncate(value)
}
