package store

import (
	"context"
	"errors"
	"fmt"

	"powerlifting/program/internal/env"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

const PointerSK = "program#current"

type NotFoundError struct{ Message string }

func (e *NotFoundError) Error() string { return e.Message }

func notFound(format string, args ...any) error {
	return &NotFoundError{Message: fmt.Sprintf(format, args...)}
}

func IsNotFound(err error) bool {
	var target *NotFoundError
	return errors.As(err, &target)
}

type Programs struct {
	DB       DB
	Tables   Tables
	Env      env.Env
	Sessions Sessions
}

func New(db DB, tables Tables, e env.Env) Programs {
	return Programs{DB: db, Tables: tables, Env: e, Sessions: Sessions{DB: db, Tables: tables, Env: e}}
}

func (p Programs) getHealth(ctx context.Context, athlete, sk string, consistent bool) (Item, error) {
	return p.DB.Get(ctx, p.Tables.Health, Key{PK: athlete, SK: sk}, GetOptions{Consistent: consistent})
}

func (p Programs) currentRef(ctx context.Context, athlete string, consistent bool) (string, error) {
	pointer, err := p.getHealth(ctx, athlete, PointerSK, consistent)
	if err != nil {
		return "", err
	}
	ref := pyval.Str2(pointer["ref_sk"])
	if ref == "" {
		return "", notFound("No program found for pk=%s. Run setup to create one.", athlete)
	}
	return ref, nil
}

func (p Programs) CurrentSK(ctx context.Context, athlete string) (string, error) {
	ref, err := p.currentRef(ctx, athlete, false)
	if err != nil {
		return "", err
	}
	program, err := p.getHealth(ctx, athlete, ref, false)
	if err != nil {
		return "", err
	}
	if program == nil {
		return "", notFound("No program found for pk=%s. Run setup to create one.", athlete)
	}
	return ref, nil
}

type Loaded struct {
	Program     map[string]any
	SK          string
	ImportID    string
	ImportClaim string
}

func (p Programs) Load(ctx context.Context, athlete string, withSessions bool) (*Loaded, error) {
	refSK, err := p.currentRef(ctx, athlete, withSessions)
	if err != nil {
		return nil, err
	}
	program, err := p.getHealth(ctx, athlete, refSK, withSessions)
	if err != nil {
		return nil, err
	}
	if program == nil {
		return nil, fmt.Errorf("Program item not found at %s. Data inconsistency: pointer exists but program item missing.", refSK)
	}
	if err := p.loadSupplements(ctx, athlete, refSK, program); err != nil {
		return nil, err
	}
	if _, ok := program["meta"].(map[string]any); !ok {
		program["meta"] = map[string]any{}
	}
	delete(program, "pk")
	delete(program, "sk")
	if withSessions {
		phases, _ := program["phases"].([]any)
		sessions, err := p.Sessions.List(ctx, athlete, refSK, phases, SessionWindow{})
		if err != nil {
			return nil, err
		}
		program["sessions"] = sessions
	}
	return &Loaded{Program: program, SK: refSK}, nil
}

type Snapshot struct {
	Program map[string]any
	SK      string
}

func (p Programs) Snapshot(ctx context.Context, athlete string) (*Snapshot, error) {
	selected, err := p.currentRef(ctx, athlete, true)
	if err != nil {
		return nil, err
	}
	program, err := p.getHealth(ctx, athlete, selected, true)
	if err != nil {
		return nil, err
	}
	if program == nil {
		return nil, notFound("Program not found: %s", selected)
	}
	if err := p.loadSupplements(ctx, athlete, selected, program); err != nil {
		return nil, err
	}
	return &Snapshot{Program: program, SK: selected}, nil
}

func (p Programs) Commit(ctx context.Context, athlete string, snapshot *Snapshot, program map[string]any) (string, error) {
	if sessions, ok := program["sessions"].([]any); ok {
		if err := ValidateIdentities(sessions); err != nil {
			return "", err
		}
	}
	now := p.Env.Stamp()
	updated := pyval.CopyMap(program)
	meta, ok := updated["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		updated["meta"] = meta
	}
	meta["updated_at"] = now
	updated["pk"] = athlete
	updated["sk"] = snapshot.SK
	delete(updated, "sessions")
	if p.Tables.Supplements != "" {
		if err := p.saveSupplementChanges(ctx, athlete, snapshot, program); err != nil {
			return "", err
		}
		removeSupplementFields(updated)
	}
	if err := p.DB.Put(ctx, p.Tables.Health, updated); err != nil {
		return "", err
	}
	return now, nil
}

type Written struct {
	Program map[string]any
	SK      string
}

func (p Programs) Save(ctx context.Context, athlete string, program map[string]any, loaded *Loaded) (*Written, error) {
	now := p.Env.Stamp()
	meta, ok := program["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		program["meta"] = meta
	}
	meta["updated_at"] = now
	sessions, _ := pyval.DeepCopy(program["sessions"]).([]any)
	if err := ValidateIdentities(sessions); err != nil {
		return nil, err
	}
	item := pyval.CopyMap(program)
	delete(item, "sessions")
	var full map[string]any
	if p.Tables.Supplements != "" {
		full = pyval.CopyMap(program)
		delete(full, "sessions")
		removeSupplementFields(item)
	}
	item["pk"] = athlete
	item["sk"] = loaded.SK
	if err := p.DB.SaveProgram(ctx, p.Tables, athlete, item, loaded.SK, scope.CurrentBlockID(program), now, loaded.ImportID, loaded.ImportClaim); err != nil {
		return nil, err
	}
	if p.Tables.Supplements != "" {
		if err := p.persistSupplements(ctx, athlete, loaded.SK, full); err != nil {
			return nil, err
		}
	}
	phases, _ := program["phases"].([]any)
	if err := p.Sessions.Sync(ctx, athlete, loaded.SK, sessions, phases); err != nil {
		return nil, err
	}
	return &Written{Program: program, SK: loaded.SK}, nil
}

func (p Programs) SetupCurrentSK(ctx context.Context, athlete string) (string, bool, error) {
	pointer, err := p.getHealth(ctx, athlete, PointerSK, true)
	if err != nil {
		return "", false, err
	}
	if ref := pyval.Str2(pointer["ref_sk"]); ref != "" {
		program, err := p.getHealth(ctx, athlete, ref, true)
		if err != nil {
			return "", false, err
		}
		if program != nil {
			return ref, true, nil
		}
	}
	return "", false, nil
}

func (p Programs) WriteInitial(ctx context.Context, athlete string, program map[string]any) (string, error) {
	sk := "program#" + p.Env.Hex()
	item := pyval.CopyMap(program)
	sessions, _ := item["sessions"].([]any)
	delete(item, "sessions")
	item["pk"] = athlete
	if err := p.persistSupplements(ctx, athlete, sk, item); err != nil {
		return "", err
	}
	if p.Tables.Supplements != "" {
		removeSupplementFields(item)
	}
	item["sk"] = sk
	if err := p.DB.Put(ctx, p.Tables.Health, item); err != nil {
		return "", err
	}
	if len(sessions) > 0 {
		phases, _ := program["phases"].([]any)
		if err := p.Sessions.WriteFresh(ctx, athlete, sk, sessions, phases); err != nil {
			return "", err
		}
	}
	pointer := Item{"pk": athlete, "sk": PointerSK, "ref_sk": sk, "updated_at": p.Env.Stamp()}
	return sk, p.DB.Put(ctx, p.Tables.Health, pointer)
}

func (p Programs) BlockNotes(ctx context.Context, athlete string) (string, Item, error) {
	sk, err := p.currentRef(ctx, athlete, false)
	if err != nil {
		if IsNotFound(err) {
			return "", nil, nil
		}
		return "", nil, err
	}
	item, err := p.DB.Get(ctx, p.Tables.Health, Key{PK: athlete, SK: sk}, GetOptions{Projection: []string{"meta.block_notes", "block_notes"}})
	return sk, item, err
}
