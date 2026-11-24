package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/xuri/excelize/v2"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
)

func TestHistoryExportsOnlyRequestedWeeks(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	svc := New(registry, accessValue{"is_self": true}, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	svc.Now = func() time.Time { return time.Date(2026, 11, 23, 0, 0, 0, 0, time.UTC) }
	svc.Programs = testLoader{program: map[string]any{"meta": map[string]any{"program_name": "Prep"}, "sessions": []any{map[string]any{"date": "2026-11-01", "week_number": 1, "day": "Old Day"}, map[string]any{"date": "2026-11-08", "week_number": 2, "day": "New Day"}}}}
	caller := auth.Caller{Person: "person", Athlete: "athlete"}
	for _, format := range []string{"markdown", "xlsx"} {
		result, err := svc.Call(context.Background(), "export_program_history", map[string]any{"format": format, "week_start": 2, "week_end": 2}, caller)
		if err != nil {
			t.Fatal(err)
		}
		out := result.(map[string]any)
		content, err := base64.StdEncoding.DecodeString(out["content_base64"].(string))
		if err != nil {
			t.Fatal(err)
		}
		if format == "markdown" {
			if strings.Contains(string(content), "Old Day") || !strings.Contains(string(content), "New Day") {
				t.Fatalf("unexpected markdown: %s", content)
			}
		} else {
			book, err := excelize.OpenReader(bytes.NewReader(content))
			if err != nil {
				t.Fatal(err)
			}
			rows, err := book.GetRows("Sessions")
			_ = book.Close()
			if err != nil || len(rows) != 2 || rows[1][1] != "2026-11-08" {
				t.Fatalf("rows=%#v err=%v", rows, err)
			}
		}
	}
}
