package render

import (
	"bytes"
	"fmt"
	"regexp"
	"strings"

	"github.com/xuri/excelize/v2"
)

const (
	sheetNameLimit = 31
	cellLimit      = 32000
)

var sheetForbidden = regexp.MustCompile(`[\\/?*\[\]:]`)

func sheetName(name string, used map[string]bool) string {
	base := strings.TrimSpace(truncate(sheetForbidden.ReplaceAllString(name, " "), sheetNameLimit))
	if base == "" {
		base = "Sheet"
	}
	candidate := base
	for suffix := 2; used[strings.ToLower(candidate)]; suffix++ {
		tail := fmt.Sprintf(" %d", suffix)
		candidate = truncate(base, sheetNameLimit-len(tail)) + tail
	}
	used[strings.ToLower(candidate)] = true
	return candidate
}

func truncate(value string, limit int) string {
	runes := []rune(value)
	if len(runes) <= limit {
		return value
	}
	return string(runes[:limit])
}

func workbook(tables []Table) ([]byte, error) {
	file := excelize.NewFile()
	defer file.Close()
	used := map[string]bool{}
	for index, table := range tables {
		name := sheetName(table.Sheet, used)
		if index == 0 {
			if err := file.SetSheetName("Sheet1", name); err != nil {
				return nil, err
			}
		} else if _, err := file.NewSheet(name); err != nil {
			return nil, err
		}
		for rowIndex, row := range table.Rows {
			cells := make([]any, len(row))
			for cellIndex, cell := range row {
				cells[cellIndex] = cellValue(cell)
			}
			address, err := excelize.CoordinatesToCellName(1, rowIndex+1)
			if err != nil {
				return nil, err
			}
			if err := file.SetSheetRow(name, address, &cells); err != nil {
				return nil, err
			}
		}
	}
	var buffer bytes.Buffer
	if err := file.Write(&buffer); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}

func cellValue(value any) any {
	switch typed := value.(type) {
	case string:
		return truncate(typed, cellLimit)
	case float64, int, bool, nil:
		return typed
	}
	return truncate(compact(value), cellLimit)
}
