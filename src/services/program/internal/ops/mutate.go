package ops

import (
	"sort"

	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

var allowedMetaFields = map[string]bool{
	"program_name": true, "program_start": true, "federation": true, "practicing_for": true,
	"version_label": true, "sex": true, "weight_class_kg": true, "weight_classes_kg": true, "weight_class_confirm_by": true,
	"current_body_weight_kg": true, "current_body_weight_lb": true, "manual_maxes": true, "lift_attempt_settings": true,
	"target_squat_kg": true, "target_bench_kg": true, "target_dl_kg": true, "target_total_kg": true,
	"attempt_pct": true, "height_cm": true, "arm_wingspan_cm": true, "leg_length_cm": true, "body_fat_range": true,
	"blocks": true,
}

type mutator func(program map[string]any) (map[string]any, error)

func (d *Deps) mutateSource(r *Request, selected string, mutate mutator) (any, error) {
	snapshot, err := d.Programs.Snapshot(r.Ctx, r.Athlete, selected)
	if err != nil {
		return nil, mapError(err)
	}
	program := pyval.CopyMap(snapshot.Program)
	result, err := mutate(program)
	if err != nil {
		return nil, err
	}
	updatedAt, err := d.Programs.Commit(r.Ctx, r.Athlete, snapshot, program)
	if err != nil {
		return nil, mapError(err)
	}
	result["sk"] = snapshot.SK
	result["updated_at"] = updatedAt
	return result, nil
}

func metaOf(program map[string]any) map[string]any {
	meta, ok := program["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		program["meta"] = meta
	}
	return meta
}

func programArchive(d *Deps, r *Request) (any, error) {
	return d.setArchived(r, true)
}

func programUnarchive(d *Deps, r *Request) (any, error) {
	return d.setArchived(r, false)
}

func (d *Deps) setArchived(r *Request, archived bool) (any, error) {
	sk := r.String("program_sk")
	if sk == "" {
		current, err := d.Programs.CurrentSK(r.Ctx, r.Athlete, "")
		if err != nil {
			return nil, mapError(err)
		}
		sk = current
	}
	snapshot, err := d.Programs.Snapshot(r.Ctx, r.Athlete, sk)
	if err != nil {
		return nil, mapError(err)
	}
	program := pyval.CopyMap(snapshot.Program)
	meta := metaOf(program)
	meta["archived"] = archived
	if archived {
		meta["archived_at"] = d.Env.Stamp()
	} else {
		meta["archived_at"] = nil
	}
	updatedAt, err := d.Programs.Commit(r.Ctx, r.Athlete, snapshot, program)
	if err != nil {
		return nil, mapError(err)
	}
	return map[string]any{"success": true, "archived": archived, "sk": snapshot.SK, "updated_at": updatedAt}, nil
}

func programUpdateMeta(d *Deps, r *Request) (any, error) {
	updates, isMap := r.Args["updates"].(map[string]any)
	if !isMap {
		field, _ := r.Args["field"].(string)
		if field == "" {
			return nil, validation("field is required")
		}
		updates = map[string]any{field: r.Args["value"]}
	}
	if len(updates) == 0 {
		return nil, validation("updates must be a nonempty object")
	}
	var unknown []string
	for key := range updates {
		if !allowedMetaFields[key] {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		names := make([]any, len(unknown))
		for index, key := range unknown {
			names[index] = key
		}
		return nil, validation("Cannot update fields: " + pyval.Repr(names))
	}
	if classes, present := updates["weight_classes_kg"]; present {
		if !validWeightClasses(classes) {
			return nil, validation("weight_classes_kg must contain at most two positive numbers")
		}
	}
	return d.mutateSource(r, r.Selected(), func(program map[string]any) (map[string]any, error) {
		meta := metaOf(program)
		for key, value := range updates {
			meta[key] = pyval.DeepCopy(value)
		}
		return map[string]any{"success": true, "meta": pyval.CopyMap(meta)}, nil
	})
}

func validWeightClasses(value any) bool {
	classes, ok := value.([]any)
	if !ok || len(classes) > 2 {
		return false
	}
	for _, item := range classes {
		if _, isBool := item.(bool); isBool || !pyval.IsNumber(item) {
			return false
		}
		if number, _ := pyval.Float(item); number <= 0 {
			return false
		}
	}
	return true
}

func programUpdatePhases(d *Deps, r *Request) (any, error) {
	phases, ok := r.Args["phases"].([]any)
	if !ok {
		if r.Args["phases"] != nil && pyval.Truthy(r.Args["phases"]) {
			return nil, validation("phases must be a list")
		}
		phases = []any{}
	}
	block := r.String("block")
	return d.mutateSource(r, r.Selected(), func(program map[string]any) (map[string]any, error) {
		existing, _ := program["phases"].([]any)
		var updated []any
		if block != "" {
			updated = []any{}
			for _, raw := range existing {
				phase, _ := raw.(map[string]any)
				current := pyval.Str2(phase["block"])
				if current == "" {
					current = "current"
				}
				if current != block {
					updated = append(updated, raw)
				}
			}
		} else {
			updated = []any{}
		}
		for _, raw := range phases {
			phase, ok := raw.(map[string]any)
			if !ok {
				return nil, validation("phases must contain objects")
			}
			record := pyval.CopyMap(phase)
			fallback := "current"
			if block != "" {
				fallback = block
			}
			if _, present := phase["block"]; !present {
				record["block"] = fallback
			}
			id := pyval.Str2(phase["block"])
			if block != "" && id == "" {
				id = block
			}
			updated = append(updated, scope.Stamp(record, program, id, ""))
		}
		program["phases"] = updated
		return map[string]any{"success": true, "phases": pyval.DeepCopy(program["phases"])}, nil
	})
}

func recordActive(record map[string]any, field string, program map[string]any) bool {
	return scope.RecordBlock(record, field, program) == scope.CurrentBlockID(program)
}

func replaceActiveRecords(program map[string]any, field string, incoming []any) []any {
	kept := []any{}
	existing, _ := program[field].([]any)
	for _, raw := range existing {
		if record, ok := raw.(map[string]any); ok && !recordActive(record, field, program) {
			kept = append(kept, pyval.DeepCopy(record))
		}
	}
	for _, raw := range incoming {
		if record, ok := raw.(map[string]any); ok && recordActive(record, field, program) {
			kept = append(kept, scope.Stamp(pyval.CopyMap(record), program, "", field))
		}
	}
	return kept
}

func blockNotesUpdate(d *Deps, r *Request) (any, error) {
	notes, ok := r.Args["block_notes"].([]any)
	if !ok {
		return nil, validation("block_notes must be a list")
	}
	selected := r.Selected()
	if version := r.String("version"); version != "" && version != "current" {
		sk, item, err := d.Programs.BlockNotes(r.Ctx, r.Athlete, version)
		if err != nil {
			return nil, mapError(err)
		}
		if item == nil {
			return nil, validation("Program version " + version + " not found")
		}
		selected = sk
	}
	self := Access(r.Access).isSelf()
	return d.mutateSource(r, selected, func(program map[string]any) (map[string]any, error) {
		meta := metaOf(program)
		active := scope.CurrentBlockID(program)
		kept := []any{}
		existing, _ := meta["block_notes"].([]any)
		for _, raw := range existing {
			if note, ok := raw.(map[string]any); ok && (scope.RecordBlock(note, "meta.block_notes", program) != active || !self && isPrivateNote(note)) {
				kept = append(kept, pyval.DeepCopy(note))
			}
		}
		for _, raw := range notes {
			if note, ok := raw.(map[string]any); ok && scope.RecordBlock(note, "meta.block_notes", program) == active {
				written := pyval.CopyMap(note)
				if !self {
					delete(written, "private")
				}
				kept = append(kept, scope.Stamp(written, program, "", "meta.block_notes"))
			}
		}
		meta["block_notes"] = kept
		scoped, _ := scope.Program(program, "")["meta"].(map[string]any)
		return map[string]any{"success": true, "block_notes": scoped["block_notes"]}, nil
	})
}

func dietNotesUpdate(d *Deps, r *Request) (any, error) {
	notes, ok := r.Args["notes"].([]any)
	if !ok {
		return nil, validation("notes must be a list")
	}
	return d.mutateSource(r, r.Selected(), func(program map[string]any) (map[string]any, error) {
		program["diet_notes"] = replaceActiveRecords(program, "diet_notes", notes)
		return map[string]any{"success": true, "diet_notes": scope.Program(program, "")["diet_notes"]}, nil
	})
}
