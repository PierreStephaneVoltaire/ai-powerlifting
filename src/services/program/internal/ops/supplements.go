package ops

import (
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

func supplementPhasesUpdate(d *Deps, r *Request) (any, error) {
	phases, ok := r.Args["phases"].([]any)
	if !ok {
		return nil, validation("phases must be a list")
	}
	return d.mutateSource(r, "", func(program map[string]any) (map[string]any, error) {
		active := scope.CurrentBlockID(program)
		if scope.Resolve(program, r.String("block_id")) != active {
			return nil, validation("supplement phases can only be changed in the current block")
		}
		incoming := make([]any, 0, len(phases))
		for _, raw := range phases {
			phase, ok := raw.(map[string]any)
			if !ok {
				return nil, validation("each supplement phase must be an object")
			}
			for _, field := range []string{"block_id", "block"} {
				if id := pyval.Str2(phase[field]); scope.Resolve(program, id) != active {
					return nil, validation("supplement phases can only be changed in the current block")
				}
			}
			written := pyval.CopyMap(phase)
			written["block_id"] = active
			if scope.RecordBlock(written, "supplement_phases", program) != active {
				return nil, validation("supplement phases can only be changed in the current block")
			}
			incoming = append(incoming, written)
		}
		program["supplement_phases"] = replaceActiveRecords(program, "supplement_phases", incoming)
		scoped := scope.Program(program, "")
		return map[string]any{
			"supplements":       pyval.DeepCopy(listOrEmpty(scoped["supplements"])),
			"supplement_phases": pyval.DeepCopy(listOrEmpty(scoped["supplement_phases"])),
		}, nil
	})
}
