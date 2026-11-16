package ops

import (
	"sort"

	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
	"powerlifting/program/internal/store"
)

func entriesToList(entries []map[string]any) []any {
	out := make([]any, len(entries))
	for index, entry := range entries {
		out[index] = entry
	}
	return out
}

func programGet(d *Deps, r *Request) (any, error) {
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, r.Selected(), false)
	if err != nil {
		return nil, mapError(err)
	}
	programSK, err := d.Programs.CurrentSK(r.Ctx, r.Athlete, r.Selected())
	if err != nil {
		return nil, mapError(err)
	}
	block, start, end := r.String("block"), r.String("window_start"), r.String("window_end")
	entries, err := d.Related.CompetitionEntries(r.Ctx, r.Athlete, start, end)
	if err != nil {
		return nil, err
	}
	program := make(map[string]any, len(loaded.Program)+1)
	for key, value := range loaded.Program {
		program[key] = value
	}
	program["competitions"] = entriesToList(entries)
	scoped := block != "" && block != scope.AllBlocks
	if scoped {
		program = scope.Program(program, block)
	}
	phases, _ := program["phases"].([]any)
	window := store.SessionWindow{Start: start, End: end, ActiveBlock: scope.CurrentBlockID(program)}
	if scoped {
		window.BlockID = block
	}
	sessions, err := d.Programs.Sessions.List(r.Ctx, r.Athlete, programSK, phases, window)
	if err != nil {
		return nil, err
	}
	program["sessions"] = sessions
	return program, nil
}

func programListFull(d *Deps, r *Request) (any, error) {
	items, err := d.Programs.List(r.Ctx, r.Athlete, r.Bool("include_archived"))
	if err != nil {
		return nil, err
	}
	selected := r.String("program_sk")
	out := []any{}
	for _, item := range items {
		if selected == "" || pyval.Str2(item["sk"]) == selected {
			out = append(out, item)
		}
	}
	return out, nil
}

func blockNotesGet(d *Deps, r *Request) (any, error) {
	version := r.String("version")
	if version == "" {
		version = "current"
	}
	sk, item, err := d.Programs.BlockNotes(r.Ctx, r.Athlete, version)
	if err != nil {
		return nil, err
	}
	if item == nil {
		return nil, validation("Program version " + version + " not found")
	}
	return map[string]any{"version": version, "sk": sk, "block_notes": notesOf(item)}, nil
}

func notesOf(item map[string]any) []any {
	meta, _ := item["meta"].(map[string]any)
	if notes, ok := meta["block_notes"].([]any); ok {
		return notes
	}
	return []any{}
}

func scopedList(program map[string]any, blockID, field string) []any {
	scoped := scope.Program(program, blockID)
	list, ok := scoped[field].([]any)
	if !ok {
		return []any{}
	}
	return list
}

func getDietNotes(d *Deps, r *Request) (any, error) {
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, "", false)
	if err != nil {
		return nil, mapError(err)
	}
	notes := scopedList(loaded.Program, r.String("block_id"), "diet_notes")
	start, end := r.String("start_date"), r.String("end_date")
	if start != "" || end != "" {
		filtered := []any{}
		for _, raw := range notes {
			note, _ := raw.(map[string]any)
			date := pyval.String(note["date"])
			if note["date"] == nil {
				date = ""
			}
			if start != "" && date < start {
				continue
			}
			if end != "" && date > end {
				continue
			}
			filtered = append(filtered, raw)
		}
		notes = filtered
	}
	sort.SliceStable(notes, func(i, j int) bool {
		a, _ := notes[i].(map[string]any)
		b, _ := notes[j].(map[string]any)
		return noteDate(a) > noteDate(b)
	})
	return notes, nil
}

func noteDate(note map[string]any) string {
	if note["date"] == nil {
		return ""
	}
	return pyval.String(note["date"])
}

func getSupplements(d *Deps, r *Request) (any, error) {
	loaded, err := d.Programs.Load(r.Ctx, r.Athlete, "", false)
	if err != nil {
		return nil, mapError(err)
	}
	scoped := scope.Program(loaded.Program, r.String("block_id"))
	return map[string]any{
		"block_id":          scope.Resolve(loaded.Program, r.String("block_id")),
		"current_block_id":  scope.CurrentBlockID(loaded.Program),
		"supplements":       listOrEmpty(scoped["supplements"]),
		"supplement_phases": listOrEmpty(scoped["supplement_phases"]),
	}, nil
}

func listOrEmpty(value any) any {
	if value == nil {
		return []any{}
	}
	return value
}

func invalidateCache(_ *Deps, _ *Request) (any, error) {
	return map[string]any{"success": true}, nil
}

func setupStatus(d *Deps, r *Request) (any, error) {
	sk, found, err := d.Programs.SetupCurrentSK(r.Ctx, r.Athlete)
	if err != nil {
		return nil, err
	}
	var current any
	if found {
		current = sk
	}
	return map[string]any{"mapped_pk": r.Athlete, "hasCurrentProgram": found, "needsSetup": !found, "currentProgramSk": current}, nil
}
