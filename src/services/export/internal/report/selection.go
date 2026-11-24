package report

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"

	"powerlifting/export/internal/scope"
)

var nonAlphanumeric = regexp.MustCompile(`[^A-Za-z0-9]+`)
var invalidFilename = regexp.MustCompile(`[^A-Za-z0-9_.-]+`)

func NormalizeFormat(value string) (string, error) {
	if value == "" {
		return "xlsx", nil
	}
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "md", "markdown":
		return "markdown", nil
	case "xlsx":
		return "xlsx", nil
	default:
		return "", fmt.Errorf("unsupported export format %q: use xlsx or markdown", value)
	}
}

func EntryWindow(program map[string]any, block string, window map[string]any, sessions []any) (string, string) {
	start, _ := window["window_start"].(string)
	end, _ := window["window_end"].(string)
	if start == "" && end == "" {
		blocks := records(object(program["meta"])["blocks"])
		sort.SliceStable(blocks, func(i, j int) bool {
			left, _ := blocks[i]["start_date"].(string)
			right, _ := blocks[j]["start_date"].(string)
			return left < right
		})
		target := scope.Resolve(program, block)
		for i, item := range blocks {
			if scope.BlockID(item) != target {
				continue
			}
			start, _ = item["start_date"].(string)
			if len(start) > 10 {
				start = start[:10]
			}
			if i+1 < len(blocks) {
				next, _ := blocks[i+1]["start_date"].(string)
				if len(next) > 10 {
					next = next[:10]
				}
				if date, err := time.Parse("2006-01-02", next); err == nil {
					end = date.AddDate(0, 0, -1).Format("2006-01-02")
				}
			}
			break
		}
	}
	dates := []string{}
	for _, raw := range sessions {
		item, _ := raw.(map[string]any)
		date, _ := item["date"].(string)
		if len(date) > 10 {
			date = date[:10]
		}
		if date != "" {
			dates = append(dates, date)
		}
	}
	sort.Strings(dates)
	if len(dates) > 0 {
		if start == "" {
			start = dates[0]
		}
		if end == "" {
			end = dates[len(dates)-1]
		}
	}
	return start, end
}

func BlockName(program map[string]any, block string) string {
	meta := object(program["meta"])
	if block == "current" || block == "" {
		block, _ = meta["current_block_id"].(string)
	}
	for _, item := range records(meta["blocks"]) {
		if item["id"] == block || item["label"] == block {
			if name, ok := item["name"].(string); ok && name != "" {
				return strings.TrimSpace(name)
			}
			break
		}
	}
	if name, ok := meta["program_name"].(string); ok && name != "" {
		return strings.TrimSpace(name)
	}
	return "program"
}

func Filename(program map[string]any, block string, window map[string]any, extension string) string {
	span := ""
	if window["week_start"] != nil && window["week_end"] != nil {
		span = fmt.Sprintf("_W%v-W%v", window["week_start"], window["week_end"])
	} else if window["window_start"] != nil || window["window_end"] != nil {
		start, _ := window["window_start"].(string)
		end, _ := window["window_end"].(string)
		if start != "" || end != "" {
			span = "_" + start + "_" + end
		}
	}
	stem := strings.ToLower(strings.Trim(nonAlphanumeric.ReplaceAllString(BlockName(program, block), "-"), "-"))
	if stem == "" {
		stem = "program"
	}
	return invalidFilename.ReplaceAllString(stem+span+"."+extension, "-")
}

func SessionsInWindow(sessions []any, window map[string]any) []any {
	startWeek, startOK := number(window["week_start"])
	endWeek, endOK := number(window["week_end"])
	start, _ := window["window_start"].(string)
	end, _ := window["window_end"].(string)
	selected := make([]any, 0, len(sessions))
	for _, raw := range sessions {
		session, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if startOK && endOK {
			week, _ := number(session["week_number"])
			if week < startWeek || week > endWeek {
				continue
			}
		} else {
			date, _ := session["date"].(string)
			if len(date) > 10 {
				date = date[:10]
			}
			if start != "" && date < start || end != "" && date > end {
				continue
			}
		}
		selected = append(selected, session)
	}
	return selected
}
