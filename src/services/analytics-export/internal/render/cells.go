package render

import (
	"bytes"
	"encoding/json"
	"math"
	"math/big"
	"sort"
	"strconv"
	"strings"
)

type Row []any

type Table struct {
	Title string
	Sheet string
	Rows  []Row
}

func record(value any) map[string]any {
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return map[string]any{}
}

func list(value any) []any {
	if typed, ok := value.([]any); ok {
		return typed
	}
	return nil
}

func number(value any) (float64, bool) {
	typed, ok := value.(float64)
	return typed, ok && !math.IsNaN(typed) && !math.IsInf(typed, 0)
}

func text(value any) string {
	typed, _ := value.(string)
	return typed
}

func numberOrBlank(value any) any {
	if typed, ok := number(value); ok {
		return typed
	}
	return ""
}

func fixed(value float64, digits int) string {
	exact := new(big.Rat).SetFloat64(value)
	negative := exact.Sign() < 0
	exact.Abs(exact)
	scale := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(digits)), nil)
	exact.Mul(exact, new(big.Rat).SetInt(scale))
	exact.Add(exact, big.NewRat(1, 2))
	rounded := new(big.Int).Div(exact.Num(), exact.Denom())
	digitsText := rounded.String()
	if digits > 0 {
		for len(digitsText) <= digits {
			digitsText = "0" + digitsText
		}
		digitsText = digitsText[:len(digitsText)-digits] + "." + digitsText[len(digitsText)-digits:]
	}
	if negative {
		return "-" + digitsText
	}
	return digitsText
}

func formatNumber(value any, digits int) string {
	if typed, ok := number(value); ok {
		return fixed(typed, digits)
	}
	return "--"
}

func formatKg(value any) string {
	if typed, ok := number(value); ok {
		return fixed(typed, 1) + " kg"
	}
	return "--"
}

func formatPct(value any) string {
	if typed, ok := number(value); ok {
		return fixed(typed*100, 1) + "%"
	}
	return "--"
}

func formatRawPct(value any) string {
	if typed, ok := number(value); ok {
		return fixed(typed, 1) + "%"
	}
	return "--"
}

func isWord(char byte) bool {
	return char == '_' || char >= '0' && char <= '9' || char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z'
}

func titleize(value string) string {
	spaced := []byte(strings.ReplaceAll(value, "_", " "))
	for index, char := range spaced {
		if char >= 'a' && char <= 'z' && (index == 0 || !isWord(spaced[index-1])) {
			spaced[index] = char - 'a' + 'A'
		}
	}
	return string(spaced)
}

func jsonText(value any) string {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return ""
	}
	return strings.TrimRight(buffer.String(), "\n")
}

var preferredKeys = []string{
	"block", "lift", "finding", "change", "experiment", "reason", "why",
	"evidence", "tradeoff", "risk", "success_metric", "confidence",
}

func compact(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return typed
	case bool:
		return strconv.FormatBool(typed)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case int:
		return strconv.Itoa(typed)
	case []any:
		parts := make([]string, 0, len(typed))
		for _, item := range typed {
			if part := compact(item); part != "" {
				parts = append(parts, part)
			}
		}
		return strings.Join(parts, "; ")
	case map[string]any:
		parts := make([]string, 0, len(preferredKeys))
		for _, key := range preferredKeys {
			if part := compact(typed[key]); part != "" {
				parts = append(parts, part)
			}
		}
		if len(parts) > 0 {
			return strings.Join(parts, " - ")
		}
	}
	return jsonText(value)
}

func markdownEscape(value any) string {
	return strings.NewReplacer("|", `\|`, "\n", "<br>").Replace(compact(value))
}

func markdownTable(rows []Row) []string {
	if len(rows) < 2 {
		return nil
	}
	headers := make([]string, len(rows[0]))
	separators := make([]string, len(rows[0]))
	for index, header := range rows[0] {
		headers[index] = compact(header)
		separators[index] = "---"
	}
	lines := []string{"| " + strings.Join(headers, " | ") + " |", "| " + strings.Join(separators, " | ") + " |"}
	for _, row := range rows[1:] {
		cells := make([]string, len(row))
		for index, cell := range row {
			cells[index] = markdownEscape(cell)
		}
		lines = append(lines, "| "+strings.Join(cells, " | ")+" |")
	}
	return lines
}

func sortedKeys(values map[string]any) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func liftRank(name string) int {
	switch {
	case strings.HasPrefix(name, "squat"):
		return 0
	case strings.HasPrefix(name, "bench"):
		return 1
	case strings.HasPrefix(name, "deadlift"):
		return 2
	}
	return 3
}

func liftOrder(values map[string]any) []string {
	keys := sortedKeys(values)
	sort.SliceStable(keys, func(a, b int) bool { return liftRank(keys[a]) < liftRank(keys[b]) })
	return keys
}

func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case float64:
		return typed != 0 && !math.IsNaN(typed)
	case string:
		return typed != ""
	}
	return true
}
