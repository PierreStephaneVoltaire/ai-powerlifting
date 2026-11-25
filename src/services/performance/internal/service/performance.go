package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"powerlifting/performance/internal/apperr"
	"sort"
	"strconv"
	"strings"
	"time"
)

func text(v any) string { s, _ := v.(string); return s }
func num(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case json.Number:
		n, _ := x.Float64()
		return n
	case int:
		return float64(x)
	}
	return 0
}

func targetNumber(value any) any {
	if value == nil {
		return nil
	}
	if s, ok := value.(string); ok {
		n, err := strconv.ParseFloat(s, 64)
		if err != nil {
			return nil
		}
		return n
	}
	return value
}
func newID() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func (s *Service) program(ctx context.Context, pk string) (map[string]any, string, error) {
	p, err := s.Store.Get(ctx, pk, "program#current")
	if err != nil {
		return nil, "", err
	}
	sk := text(p["ref_sk"])
	if sk == "" {
		return nil, "", apperr.NotFound("Program not found")
	}
	program, err := s.Store.Get(ctx, pk, sk)
	if err != nil {
		return nil, "", err
	}
	if program == nil {
		return nil, "", apperr.NotFound("Program not found: %s", sk)
	}
	return program, sk, nil
}
func (s *Service) performance(ctx context.Context, name string, a, access map[string]any) (any, error) {
	pk := text(a["pk"])
	now := s.Now().UTC().Format(time.RFC3339Nano)
	switch name {
	case "health_get_current_maxes", "health_update_current_maxes", "max_target_get", "max_target_update":
		p, sk, err := s.program(ctx, pk)
		if err != nil {
			return nil, err
		}
		if strings.HasPrefix(name, "health_") {
			maxes, _ := p["current_maxes"].(map[string]any)
			if maxes == nil {
				maxes = map[string]any{}
			}
			if name == "health_update_current_maxes" {
				for _, lift := range []string{"squat", "bench", "deadlift"} {
					if value, ok := a[lift+"_kg"]; ok && value != nil {
						maxes[lift] = value
					}
				}
				p["current_maxes"] = maxes
				if err = s.commit(ctx, p, now); err != nil {
					return nil, err
				}
			}
			return maxes, nil
		}
		meta, _ := p["meta"].(map[string]any)
		if meta == nil {
			meta = map[string]any{}
			p["meta"] = meta
		}
		if name == "max_target_update" {
			meta["target_squat_kg"], meta["target_bench_kg"], meta["target_dl_kg"] = a["squat_kg"], a["bench_kg"], a["deadlift_kg"]
			meta["target_total_kg"] = num(a["squat_kg"]) + num(a["bench_kg"]) + num(a["deadlift_kg"])
			if err = s.commit(ctx, p, now); err != nil {
				return nil, err
			}
		}
		result := map[string]any{"sk": sk, "squat_kg": targetNumber(meta["target_squat_kg"]), "bench_kg": targetNumber(meta["target_bench_kg"]), "deadlift_kg": targetNumber(meta["target_dl_kg"]), "total_kg": targetNumber(meta["target_total_kg"])}
		if name == "max_target_update" {
			result["updated_at"] = now
		}
		return result, nil
	case "max_history_add":
		sk := "max_history#current"
		record, err := s.Store.Get(ctx, pk, sk)
		if err != nil {
			return nil, err
		}
		if record == nil {
			record = map[string]any{}
		}
		source, _ := a["entry"].(map[string]any)
		if len(source) == 0 {
			source = a
		}
		entry := map[string]any{}
		for _, key := range []string{"id", "entry_id", "date", "squat_kg", "bench_kg", "deadlift_kg", "total_kg", "bodyweight_kg", "context"} {
			if v, ok := source[key]; ok {
				entry[key] = v
			}
		}
		if text(entry["id"]) == "" {
			entry["id"] = newID()
		}
		if entry["total_kg"] == nil {
			entry["total_kg"] = num(entry["squat_kg"]) + num(entry["bench_kg"]) + num(entry["deadlift_kg"])
		}
		values, _ := record["entries"].([]any)
		entries := []any{}
		for _, raw := range values {
			v, _ := raw.(map[string]any)
			if text(v["id"]) != text(entry["id"]) {
				entries = append(entries, raw)
			}
		}
		entries = append(entries, entry)
		sortEntries(entries)
		record["pk"], record["sk"], record["entries"], record["updated_at"] = pk, sk, entries, now
		if err = s.Store.Put(ctx, record); err != nil {
			return nil, err
		}
		filtered := []any{}
		for _, raw := range entries {
			if item, ok := raw.(map[string]any); ok && visible(item, access) {
				filtered = append(filtered, item)
			}
		}
		record["entries"] = filtered
		return record, nil
	case "max_history_get":
		return s.history(ctx, pk, a, access, now)
	}
	return nil, apperr.UnknownOperation()
}
func (s *Service) commit(ctx context.Context, p map[string]any, now string) error {
	meta, _ := p["meta"].(map[string]any)
	if meta == nil {
		meta = map[string]any{}
		p["meta"] = meta
	}
	meta["updated_at"] = now
	delete(p, "sessions")
	return s.Store.Put(ctx, p)
}
func sortEntries(entries []any) {
	sort.SliceStable(entries, func(i, j int) bool {
		a, _ := entries[i].(map[string]any)
		b, _ := entries[j].(map[string]any)
		return text(a["date"]) > text(b["date"])
	})
}
func visible(entry map[string]any, access map[string]any) bool {
	scope, _ := access["competition_scope"].(map[string]any)
	raw, limited := scope["read"]
	if !limited || raw == nil {
		return true
	}
	id := text(entry["entry_id"])
	if id == "" {
		return text(entry["context"]) != "Competition result"
	}
	id = strings.TrimPrefix(strings.TrimPrefix(id, "competition#"), "COMP#")
	allowed, _ := raw.([]any)
	for _, v := range allowed {
		if strings.TrimPrefix(text(v), "COMP#") == id {
			return true
		}
	}
	return false
}
func (s *Service) history(ctx context.Context, pk string, a, access map[string]any, now string) (any, error) {
	start, end := text(a["start_date"]), text(a["end_date"])
	if start != "" && end != "" && start > end {
		return nil, apperr.Validation("start_date must be on or before end_date")
	}
	sk := "max_history#current"
	record, err := s.Store.Get(ctx, pk, sk)
	if err != nil {
		return nil, err
	}
	if record == nil {
		record = map[string]any{"pk": pk, "sk": sk, "entries": []any{}, "updated_at": now}
	}
	keyed := map[string]map[string]any{}
	manual := []any{}
	values, _ := record["entries"].([]any)
	for _, raw := range values {
		entry, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if id := text(entry["entry_id"]); id != "" {
			keyed[id] = entry
			continue
		}
		if text(entry["id"]) == "" {
			b, _ := json.Marshal(entry)
			h := sha256.Sum256(b)
			entry["id"] = "max-" + hex.EncodeToString(h[:12])
		}
		manual = append(manual, entry)
	}
	competitions, err := s.Store.Competitions(ctx, pk)
	if err != nil {
		return nil, err
	}
	for _, meet := range competitions {
		results, ok := meet["results"].(map[string]any)
		if !ok || meet["user_status"] != "completed" {
			continue
		}
		id := text(meet["master_id"])
		if id == "" {
			id = strings.TrimPrefix(text(meet["sk"]), "COMP#")
		}
		identifier := "competition#" + id
		date := text(meet["start_date"])
		if date == "" {
			date = text(meet["date"])
		}
		entry := map[string]any{"entry_id": identifier, "date": date, "context": "Competition result", "bodyweight_kg": meet["body_weight_kg"], "squat_kg": results["squat_kg"], "bench_kg": results["bench_kg"], "deadlift_kg": results["deadlift_kg"], "total_kg": results["total_kg"]}
		if num(entry["total_kg"]) == 0 {
			entry["total_kg"] = num(entry["squat_kg"]) + num(entry["bench_kg"]) + num(entry["deadlift_kg"])
		}
		for _, field := range []string{"squat_kg", "bench_kg", "deadlift_kg", "bodyweight_kg"} {
			if entry[field] == nil {
				delete(entry, field)
			}
		}
		keyed[identifier] = entry
	}
	for _, entry := range keyed {
		manual = append(manual, entry)
	}
	out := []any{}
	for _, raw := range manual {
		entry, _ := raw.(map[string]any)
		for _, field := range []string{"squat_kg", "bench_kg", "deadlift_kg", "total_kg", "bodyweight_kg"} {
			if entry[field] == nil {
				delete(entry, field)
			}
		}
		date := text(entry["date"])
		if visible(entry, access) && (start == "" || date >= start) && (end == "" || date <= end) {
			out = append(out, entry)
		}
	}
	sortEntries(out)
	record["entries"] = out
	return record, nil
}
