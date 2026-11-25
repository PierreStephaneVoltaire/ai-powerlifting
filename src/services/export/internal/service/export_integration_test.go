package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/xuri/excelize/v2"
	"powerlifting/export/internal/auth"
	"powerlifting/export/internal/contract"
	"powerlifting/export/internal/hydration"
)

type exportReader struct{}

func (exportReader) Get(_ context.Context, table, _, key string) (map[string]any, error) {
	if table == "health" && key == "program#current" {
		return map[string]any{"ref_sk": "program#v001"}, nil
	}
	if table == "health" && key == "program#v001" {
		return map[string]any{"meta": map[string]any{"program_name": "Prep", "current_block_id": "active", "blocks": []any{map[string]any{"id": "active", "status": "active"}}, "block_notes": []any{map[string]any{"notes": "private note", "private": true}, map[string]any{"notes": "shared note"}}}}, nil
	}
	return nil, nil
}
func (exportReader) Query(_ context.Context, table, _, prefix string) ([]map[string]any, error) {
	if table != "sessions" {
		return nil, nil
	}
	return []map[string]any{{"sk": prefix + "one", "block_id": "active", "date": "2026-11-01", "week_number": 1, "day": "Visible session", "videos": []any{map[string]any{"notes": "private video"}}}}, nil
}
func (exportReader) Competitions(context.Context, string, string, string) ([]map[string]any, error) {
	return []map[string]any{{"master_id": "shared", "name": "Shared meet", "user_status": "confirmed"}, {"master_id": "private", "name": "Private meet", "user_status": "confirmed"}}, nil
}

func TestHistoryExportsHonorDelegatedAccess(t *testing.T) {
	registry, err := contract.Load()
	if err != nil {
		t.Fatal(err)
	}
	access := accessValue{"permissions": []any{"program:read", "sessions:read", "competition:read"}, "granted_permissions": []any{"sessions:read"}, "competition_scope": map[string]any{"read": []any{"shared"}}}
	svc := New(registry, access, nil, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	svc.Programs = hydration.Loader{Reader: exportReader{}, Tables: hydration.Tables{Health: "health", Sessions: "sessions", Supplements: "supplements"}}
	caller := auth.Caller{Person: "coach", Athlete: "athlete"}
	for _, format := range []string{"markdown", "xlsx"} {
		result, err := svc.Call(context.Background(), "export_program_history", map[string]any{"format": format}, caller)
		if err != nil {
			t.Fatal(err)
		}
		content, err := base64.StdEncoding.DecodeString(result.(map[string]any)["content_base64"].(string))
		if err != nil {
			t.Fatal(err)
		}
		text := string(content)
		if format == "xlsx" {
			book, err := excelize.OpenReader(bytes.NewReader(content))
			if err != nil {
				t.Fatal(err)
			}
			var cells []string
			for _, name := range book.GetSheetList() {
				rows, err := book.GetRows(name)
				if err != nil {
					t.Fatal(err)
				}
				for _, row := range rows {
					cells = append(cells, row...)
				}
			}
			text = strings.Join(cells, " ")
			_ = book.Close()
		}
		for _, secret := range []string{"private note", "private video", "Private meet"} {
			if strings.Contains(text, secret) {
				t.Errorf("%s leaked %q", format, secret)
			}
		}
		for _, visible := range []string{"Visible session", "Shared meet", "shared note"} {
			if !strings.Contains(text, visible) {
				t.Errorf("%s missing %q", format, visible)
			}
		}
	}
}
