package service

import (
	"sort"
	"time"
)

type block struct{ id, start, status string }

func text(v any) string { s, _ := v.(string); return s }
func blockState(program map[string]any) (string, []block) {
	meta, _ := program["meta"].(map[string]any)
	current := text(meta["current_block_id"])
	var blocks []block
	list, _ := meta["blocks"].([]any)
	for _, raw := range list {
		b, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		id := text(b["id"])
		if id == "" {
			id = text(b["block_id"])
		}
		if id == "" {
			continue
		}
		start := text(b["start_date"])
		if len(start) >= 10 {
			start = start[:10]
		}
		if _, err := time.Parse("2006-01-02", start); err != nil {
			start = ""
		}
		blocks = append(blocks, block{id, start, text(b["status"])})
	}
	sort.SliceStable(blocks, func(i, j int) bool {
		if blocks[i].start == blocks[j].start {
			return blocks[i].id < blocks[j].id
		}
		return blocks[i].start < blocks[j].start
	})
	if current == "" || current == "current" {
		for _, b := range blocks {
			if b.status == "active" {
				current = b.id
			}
		}
	}
	if current == "" {
		current = "current"
	}
	return current, blocks
}
func belongs(entry map[string]any, active string, blocks []block) string {
	date := text(entry["date"])
	if len(date) >= 10 {
		date = date[:10]
	}
	if _, err := time.Parse("2006-01-02", date); err == nil {
		var dated []block
		for _, b := range blocks {
			if b.start != "" {
				dated = append(dated, b)
			}
		}
		if len(dated) > 0 {
			for _, b := range dated {
				if b.id == active && date >= b.start {
					return active
				}
			}
			chosen := dated[0].id
			for _, b := range dated {
				if b.start > date {
					break
				}
				chosen = b.id
			}
			return chosen
		}
	}
	id := text(entry["block_id"])
	if id == "" {
		id = text(entry["block"])
	}
	if id == "" || id == "current" {
		return active
	}
	return id
}
