package ops

import (
	"time"

	"powerlifting/program/internal/pyval"
)

func templateHasLoggedWork(session map[string]any) bool {
	if pyval.Truthy(session["completed"]) {
		return true
	}
	switch pyval.Str2(session["status"]) {
	case "logged", "completed", "skipped":
		return true
	}
	for _, exercise := range pyval.Maps(session["exercises"]) {
		statuses, _ := exercise["set_statuses"].([]any)
		for _, status := range statuses {
			if pyval.Str2(status) != "pending" {
				return true
			}
		}
		if pyval.Truthy(exercise["sets_completed"]) || exercise["actual_kg"] != nil {
			return true
		}
	}
	return false
}

func templateApplySessions(d *Deps, r *Request) (any, error) {
	target := r.String("target")
	if target != "append" && target != "replace_incomplete" {
		return nil, validation("target must be append or replace_incomplete")
	}
	if _, err := time.Parse("2006-01-02", r.String("start_date")); err != nil {
		return nil, validation("Invalid start date")
	}
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, "", true)
	if err != nil {
		return nil, mapError(err)
	}
	program := pyval.CopyMap(loaded.Program)
	meta := metaOf(program)
	operationID := r.String("operation_id")
	receipts, _ := meta["template_operations"].(map[string]any)
	if receipt, ok := receipts[operationID].(map[string]any); operationID != "" && ok {
		result := pyval.CopyMap(receipt)
		result["program_sk"] = loaded.SK
		result["program_version"] = meta["version_label"]
		return result, nil
	}
	blocks := pyval.Maps(meta["blocks"])
	targetID := r.String("block_id")
	if targetID == "" {
		for _, block := range blocks {
			if blockStatus(block) == "active" {
				targetID = idOf(block)
				break
			}
		}
	}
	if targetID == "" {
		targetID = pyval.Str2(meta["current_block_id"])
	}
	if targetID == "" {
		targetID = "current"
	}
	found := len(blocks) == 0 && targetID == "current"
	for _, block := range blocks {
		if idOf(block) == targetID {
			if blockStatus(block) != "active" {
				return nil, validation("Template sessions may only target the active block")
			}
			block["week_start_day"] = r.Args["week_start_day"]
			found = true
		}
	}
	if !found {
		return nil, validation("block_id must identify an existing block")
	}
	existing := pyval.Maps(program["sessions"])
	incoming := pyval.Maps(r.Args["sessions"])
	dates := map[string]bool{}
	for _, session := range incoming {
		date := pyval.Str2(session["date"])
		if _, err := time.Parse("2006-01-02", date); err != nil {
			return nil, validation("Invalid session date")
		}
		dates[date] = true
	}
	logged := map[string]bool{}
	merged := make([]any, 0, len(existing)+len(incoming))
	for _, session := range existing {
		date := pyval.Str2(session["date"])
		hasWork := templateHasLoggedWork(session)
		if hasWork {
			logged[date] = true
		}
		if target == "append" || !dates[date] || hasWork {
			merged = append(merged, session)
		}
	}
	for _, session := range incoming {
		if target == "replace_incomplete" && logged[pyval.Str2(session["date"])] {
			continue
		}
		id := d.Env.UUID()
		session["id"], session["session_id"] = id, id
		session["status"], session["completed"] = "planned", false
		session["block"], session["block_id"] = "current", targetID
		merged = append(merged, session)
	}
	program["sessions"] = merged
	meta["blocks"] = pyval.ToList(blocks)
	meta["template_lineage"] = map[string]any{"applied_template_sk": r.String("sk"), "applied_at": d.Env.Stamp(), "week_start_day": r.Args["week_start_day"], "start_date": r.Args["start_date"]}
	result := map[string]any{"status": "applied", "target": target, "block_id": targetID, "preserved_sessions": len(existing)}
	if operationID != "" {
		if receipts == nil {
			receipts = map[string]any{}
			meta["template_operations"] = receipts
		}
		receipts[operationID] = pyval.CopyMap(result)
	}
	written, err := d.Programs.WriteNewVersion(r.Ctx, r.Athlete, program, false, loaded)
	if err != nil {
		return nil, mapError(err)
	}
	result["program_version"], result["program_sk"] = meta["version_label"], written.SK
	return result, nil
}
