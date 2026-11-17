package service

import (
	"context"
	"powerlifting/federation/internal/apperr"
	"slices"
	"strings"
	"time"
)

func text(v any) string { s, _ := v.(string); return s }
func normalizeMaster(item map[string]any, now string) map[string]any {
	out := map[string]any{"pk": text(item["pk"]), "sk": text(item["sk"]), "name": text(item["name"]), "status": "active", "has_standards": false, "standards": map[string]any{}, "created_at": now, "updated_at": now}
	for _, key := range []string{"abbreviation", "region", "website_url", "source_slug", "parent_federation_abbr"} {
		out[key] = nil
		if v, ok := item[key].(string); ok {
			out[key] = v
		}
	}
	if item["status"] == "archived" {
		out["status"] = "archived"
	}
	if value, ok := item["has_standards"].(bool); ok {
		out["has_standards"] = value
	}
	if v, ok := item["standards"].(map[string]any); ok {
		out["standards"] = v
	}
	out["standard_unit"] = nil
	if v := text(item["standard_unit"]); v == "kg" || v == "dots" {
		out["standard_unit"] = v
	}
	for _, key := range []string{"created_at", "updated_at"} {
		if v := text(item[key]); v != "" {
			out[key] = v
		}
	}
	if v, ok := item["display_options"].(map[string]any); ok {
		out["display_options"] = v
	}
	if v, ok := item["membership_group"].([]any); ok {
		out["membership_group"] = v
	}
	return out
}
func (s *Service) federation(ctx context.Context, name string, args map[string]any) (any, error) {
	now := s.Now().UTC().Format(time.RFC3339Nano)
	pk := text(args["pk"])
	switch name {
	case "federation_master_list":
		items, err := s.Store.List(ctx)
		if err != nil {
			return nil, err
		}
		out := make([]any, 0, len(items))
		for _, item := range items {
			out = append(out, normalizeMaster(item, now))
		}
		return out, nil
	case "federation_master_update":
		id := strings.TrimSpace(text(args["master_id"]))
		updates, _ := args["updates"].(map[string]any)
		if id == "" || len(updates) == 0 {
			return nil, apperr.Validation("master_id and updates are required")
		}
		allowed := []string{"name", "abbreviation", "region", "website_url", "status", "source_slug", "has_standards", "standard_unit", "standards", "display_options", "parent_federation_abbr", "membership_group"}
		for key := range updates {
			if !slices.Contains(allowed, key) {
				return nil, apperr.Validation("unsupported federation field: " + key)
			}
		}
		updates["updated_at"] = now
		if err := s.Store.Update(ctx, id, updates); err != nil {
			return nil, err
		}
		return map[string]any{"success": true}, nil
	case "federation_user_library_get":
		item, err := s.Store.Get(ctx, pk)
		if err != nil {
			return nil, err
		}
		if item == nil {
			item = map[string]any{"pk": pk, "sk": "federations#v1", "updated_at": now, "federations": []any{}, "qualification_standards": []any{}}
		}
		return item, nil
	case "federation_user_library_set":
		item := map[string]any{"pk": pk, "sk": "federations#v1", "updated_at": now, "federations": args["federations"], "qualification_standards": args["qualification_standards"]}
		if err := s.Store.Put(ctx, item); err != nil {
			return nil, err
		}
		return item, nil
	}
	return nil, apperr.UnknownOperation()
}
