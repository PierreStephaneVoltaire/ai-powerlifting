package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"math"
	"slices"
	"strconv"
	"time"
)

func text(v any) string { s, _ := v.(string); return s }
func id() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return "goal-" + hex.EncodeToString(b)
}
func number(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case json.Number:
		x, _ := n.Float64()
		return x
	case int:
		return float64(n)
	}
	return 0
}
func normalize(raw map[string]any) map[string]any {
	goalID := text(raw["id"])
	if goalID == "" {
		goalID = id()
	}
	kind := text(raw["goal_type"])
	if !slices.Contains([]string{"hit_total", "qualify_for_federation", "peak_for_meet", "conservative_pr", "competition_exposure", "improve_dots", "improve_ipf_gl", "custom"}, kind) {
		kind = "custom"
	}
	priority := text(raw["priority"])
	if !slices.Contains([]string{"primary", "secondary", "optional"}, priority) {
		priority = "secondary"
	}
	out := map[string]any{"id": goalID, "title": text(raw["title"]), "goal_type": kind, "priority": priority}
	for _, key := range []string{"target_date", "notes"} {
		if value, ok := raw[key].(string); ok && (key == "notes" || value != "") {
			out[key] = value
		}
	}
	if age := text(raw["age_class"]); slices.Contains([]string{"open", "subjunior", "junior", "master1", "master2", "master3", "master4"}, age) {
		out["age_class"] = age
	}
	for _, key := range []string{"target_total_kg", "target_dots", "target_ipf_gl"} {
		n := number(raw[key])
		if n > 0 && !math.IsInf(n, 0) {
			out[key] = n
		}
	}
	for _, key := range []string{"target_competition_ids", "target_federation_ids", "target_weight_class_kg"} {
		list, _ := raw[key].([]any)
		filtered := []any{}
		seen := map[string]bool{}
		for _, v := range list {
			var token string
			if key == "target_weight_class_kg" {
				n := number(v)
				if n <= 0 || math.IsInf(n, 0) {
					continue
				}
				v = n
				token = strconv.FormatFloat(n, 'g', -1, 64)
			} else {
				v = text(v)
				token = v.(string)
				if token == "" {
					continue
				}
			}
			if !seen[token] {
				filtered = append(filtered, v)
				seen[token] = true
			}
		}
		if len(filtered) > 0 {
			out[key] = filtered
		}
	}
	return out
}
func (s *Service) goals(ctx context.Context, name string, args map[string]any) (any, error) {
	pk := text(args["pk"])
	existing, err := s.Store.List(ctx, pk)
	if err != nil {
		return nil, err
	}
	if name == "goals_list" {
		out := make([]any, 0, len(existing))
		for _, item := range existing {
			out = append(out, normalize(item))
		}
		return out, nil
	}
	byID := map[string]map[string]any{}
	for _, item := range existing {
		byID[text(item["id"])] = item
	}
	incoming := map[string]bool{}
	goals, _ := args["goals"].([]any)
	now := s.Now().UTC().Format(time.RFC3339Nano)
	for _, raw := range goals {
		input, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		goal := normalize(input)
		goalID := text(goal["id"])
		incoming[goalID] = true
		current := byID[goalID]
		created := text(current["created_at"])
		if created == "" {
			created = now
		}
		goal["created_at"], goal["updated_at"], goal["pk"], goal["sk"] = created, now, pk, "GOAL#"+goalID
		if current != nil {
			if links, ok := current["target_competition_ids"]; ok {
				goal["target_competition_ids"] = links
			} else {
				goal["target_competition_ids"] = []any{}
			}
		} else if _, ok := goal["target_competition_ids"]; !ok {
			goal["target_competition_ids"] = []any{}
		}
		if err = s.Store.Put(ctx, goal); err != nil {
			return nil, err
		}
	}
	for _, item := range existing {
		goalID := text(item["id"])
		if !incoming[goalID] {
			if err = s.Store.Delete(ctx, pk, goalID); err != nil {
				return nil, err
			}
		}
	}
	return map[string]any{"success": true}, nil
}
