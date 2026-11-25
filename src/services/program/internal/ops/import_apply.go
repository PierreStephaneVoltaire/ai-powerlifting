package ops

import (
	"sort"
	"time"

	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/store"
)

func importSessions(existing, staged []map[string]any, start, strategy string, resolutions []map[string]any) ([]any, int, int, error) {
	if len(staged) == 0 {
		return nil, 0, 0, validation("No sessions found in staged import")
	}
	if strategy != "append" && strategy != "overwrite" && strategy != "overwrite_future" && strategy != "selective" {
		return nil, 0, 0, validation("Invalid merge strategy")
	}
	actions := map[string]string{}
	for _, resolution := range resolutions {
		action := pyval.Str2(resolution["action"])
		switch action {
		case "skip", "overwrite", "replace_planned", "merge", "append":
		default:
			return nil, 0, 0, validation("Invalid conflict resolution")
		}
		actions[pyval.Str2(resolution["session_date"])] = action
	}
	if start != "" {
		target, err := time.Parse("2006-01-02", start)
		if err != nil {
			return nil, 0, 0, validation("Invalid start date")
		}
		var earliest time.Time
		for _, session := range staged {
			if date := pyval.Str2(session["date"]); date != "" {
				parsed, err := time.Parse("2006-01-02", date)
				if err != nil {
					return nil, 0, 0, validation("Invalid session date")
				}
				if earliest.IsZero() || parsed.Before(earliest) {
					earliest = parsed
				}
			}
		}
		if !earliest.IsZero() {
			days := int((target.Unix() - earliest.Unix()) / 86400)
			for _, session := range staged {
				if date := pyval.Str2(session["date"]); date != "" {
					parsed, _ := time.Parse("2006-01-02", date)
					session["date"] = parsed.AddDate(0, 0, days).Format("2006-01-02")
				}
			}
		}
	}
	byDate := map[string]map[string]any{}
	for _, session := range existing {
		if date := pyval.Str2(session["date"]); date != "" {
			byDate[date] = session
		}
	}
	applied, skipped := 0, 0
	for _, session := range staged {
		date := pyval.Str2(session["date"])
		if date == "" {
			continue
		}
		current := byDate[date]
		if current == nil {
			existing = append(existing, session)
			byDate[date] = session
			applied++
			continue
		}
		action := actions[date]
		if action == "" {
			action = strategy
			if action == "overwrite_future" {
				action = "overwrite"
			}
			if action == "selective" {
				action = "skip"
			}
		}
		switch action {
		case "skip":
			skipped++
		case "overwrite", "replace_planned":
			for key, value := range session {
				current[key] = value
			}
			applied++
		case "append", "merge":
			for _, field := range []string{"exercises", "planned_exercises"} {
				original, _ := current[field].([]any)
				additions, _ := session[field].([]any)
				current[field] = append(original, additions...)
			}
			applied++
		}
	}
	sort.SliceStable(existing, func(i, j int) bool { return pyval.Str2(existing[i]["date"]) < pyval.Str2(existing[j]["date"]) })
	return pyval.ToList(existing), applied, skipped, nil
}

func programApplySessionImport(d *Deps, r *Request) (any, error) {
	importID, claimID := r.String("import_id"), r.String("claim_id")
	if importID == "" || claimID == "" {
		return nil, validation("Import claim is required")
	}
	claim, err := d.Programs.DB.Get(r.Ctx, d.Programs.Tables.Health, store.Key{PK: r.Athlete, SK: "import#pending#" + importID}, store.GetOptions{Consistent: true})
	if err != nil {
		return nil, err
	}
	if pyval.Str2(claim["status"]) != "applying" || pyval.Str2(claim["apply_claim_id"]) != claimID {
		return nil, validation("Import claim is not active")
	}
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, true)
	if err != nil {
		return nil, mapError(err)
	}
	program := pyval.CopyMap(loaded.Program)
	meta := metaOf(program)
	receipts, _ := meta["session_imports"].(map[string]any)
	if receipt, ok := receipts[importID].(map[string]any); ok {
		return pyval.CopyMap(receipt), nil
	}
	strategy := r.String("merge_strategy")
	if strategy == "" {
		strategy = "append"
	}
	staged := pyval.Maps(pyval.DeepCopy(r.Args["sessions"]))
	merged, applied, skipped, err := importSessions(pyval.Maps(program["sessions"]), staged, r.String("start_date"), strategy, pyval.Maps(r.Args["conflict_resolutions"]))
	if err != nil {
		return nil, err
	}
	program["sessions"] = merged
	result := map[string]any{"status": "applied", "applied_count": applied, "skipped_count": skipped}
	if receipts == nil {
		receipts = map[string]any{}
		meta["session_imports"] = receipts
	}
	receipts[importID] = result
	loaded.ImportID, loaded.ImportClaim = importID, claimID
	if _, err := d.Programs.Save(r.Ctx, r.Athlete, program, loaded); err != nil {
		return nil, mapError(err)
	}
	return result, nil
}
