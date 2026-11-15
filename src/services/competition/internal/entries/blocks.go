package entries

import (
	"context"
	"sort"
	"time"

	"powerlifting/competition/internal/projection"
	"powerlifting/competition/internal/pyval"
	"powerlifting/competition/internal/store"
)

const activeBlock = "current"

func blockID(block map[string]any) string {
	return pyval.Str(textOr(pyval.Or(block["id"], block["block_id"]), ""))
}

func textOr(value any, fallback string) any {
	if pyval.Truthy(value) {
		return value
	}
	return fallback
}

type blockRef struct {
	id    string
	start time.Time
}

func activeBlocks(meta map[string]any) []blockRef {
	blocks, _ := meta["blocks"].([]any)
	var active []blockRef
	for _, raw := range blocks {
		block, ok := raw.(map[string]any)
		if !ok || blockID(block) == "" || block["status"] != "active" {
			continue
		}
		ref := blockRef{id: blockID(block)}
		if start := pyval.Or(block["start_date"], ""); pyval.Truthy(start) {
			text := pyval.Str(start)
			if len(text) > 10 {
				text = text[:10]
			}
			if day, ok := projection.ParseDay(text); ok {
				ref.start = day
			}
		}
		active = append(active, ref)
	}
	sort.SliceStable(active, func(i, j int) bool {
		if !active[i].start.Equal(active[j].start) {
			return active[i].start.Before(active[j].start)
		}
		return active[i].id < active[j].id
	})
	return active
}

func currentBlockID(program map[string]any) string {
	meta, _ := program["meta"].(map[string]any)
	configured := ""
	if value := meta["current_block_id"]; pyval.Truthy(value) {
		configured = pyval.Str(value)
	}
	if configured != "" && configured != activeBlock {
		return configured
	}
	if active := activeBlocks(meta); len(active) > 0 {
		return active[len(active)-1].id
	}
	if configured != "" {
		return configured
	}
	return activeBlock
}

func ActiveBlockID(ctx context.Context, programs store.Programs, pk string) (string, error) {
	pointer, err := programs.Pointer(ctx, pk)
	if err != nil {
		return "", err
	}
	if configured := pointer["current_block_id"]; pyval.Truthy(configured) && configured != activeBlock {
		return pyval.Str(configured), nil
	}
	if !pyval.Truthy(pointer["ref_sk"]) {
		return currentBlockID(pointer), nil
	}
	program, err := programs.Item(ctx, pk, pyval.Str(pointer["ref_sk"]))
	if err != nil {
		return "", err
	}
	return currentBlockID(program), nil
}

func recordBlockKey(record map[string]any) string {
	return pyval.Str(textOr(pyval.Or(record["block_id"], record["block"]), ""))
}

func inBlock(record map[string]any, block, active string) bool {
	key := recordBlockKey(record)
	if block == active || block == activeBlock {
		return key == active || key == activeBlock
	}
	return key == block
}
