package store

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"powerlifting/program/internal/env"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/scope"
)

const (
	PointerSK     = "program#current"
	ProgramPrefix = "program#v"
)

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

func unselected(selected string) bool {
	return selected == "" || selected == "current" || selected == PointerSK
}

func published(item Item) bool {
	value, present := item["published"]
	if !present {
		return true
	}
	flag, isBool := value.(bool)
	return !(isBool && !flag)
}

func (p Programs) getHealth(ctx context.Context, athlete, sk string, consistent bool) (Item, error) {
	return p.DB.Get(ctx, p.Tables.Health, Key{PK: athlete, SK: sk}, GetOptions{Consistent: consistent})
}

func (p Programs) ListVersions(ctx context.Context, athlete string, consistent bool) ([]Item, error) {
	return p.DB.Query(ctx, Query{Table: p.Tables.Health, PK: athlete, Prefix: ProgramPrefix, Consistent: consistent})
}

func (p Programs) List(ctx context.Context, athlete string, includeArchived bool) ([]Item, error) {
	items, err := p.ListVersions(ctx, athlete, false)
	if err != nil {
		return nil, err
	}
	out := make([]Item, 0, len(items))
	for _, item := range items {
		if !published(item) {
			continue
		}
		if !includeArchived {
			meta, _ := item["meta"].(map[string]any)
			if pyval.Truthy(meta["archived"]) {
				continue
			}
		}
		out = append(out, item)
	}
	return out, nil
}

func (p Programs) CurrentSK(ctx context.Context, athlete, selected string) (string, error) {
	if !unselected(selected) {
		return selected, nil
	}
	pointer, err := p.getHealth(ctx, athlete, PointerSK, false)
	if err != nil {
		return "", err
	}
	if ref := pyval.Str2(pointer["ref_sk"]); ref != "" {
		program, err := p.getHealth(ctx, athlete, ref, false)
		if err != nil {
			return "", err
		}
		if program != nil && published(program) {
			return ref, nil
		}
	}
	programs, err := p.List(ctx, athlete, false)
	if err != nil {
		return "", err
	}
	if len(programs) == 0 {
		return "", notFound("No program or pointer found for pk=%s. Create a program using new_version() first.", athlete)
	}
	sort.SliceStable(programs, func(i, j int) bool { return pyval.Str(programs[i]["sk"]) > pyval.Str(programs[j]["sk"]) })
	return pyval.Str(programs[0]["sk"]), nil
}

type Loaded struct {
	Program map[string]any
	SK      string
	Version int
}

func (p Programs) Load(ctx context.Context, athlete, selected string, withSessions bool) (*Loaded, error) {
	var pointer Item
	if !unselected(selected) {
		pointer = Item{"ref_sk": selected, "version": int64(0)}
	} else {
		found, err := p.getHealth(ctx, athlete, PointerSK, false)
		if err != nil {
			return nil, err
		}
		pointer = found
		if pointer == nil {
			if pointer, err = p.rebuildPointer(ctx, athlete); err != nil {
				return nil, err
			}
		}
	}
	version := 0
	if value, ok := pointer["version"]; ok {
		version = pyval.Int(value, 0)
	}
	refSK := pyval.Str2(pointer["ref_sk"])
	if _, present := pointer["ref_sk"]; !present {
		refSK = fmt.Sprintf("%s%03d", ProgramPrefix, version)
	}
	program, err := p.getHealth(ctx, athlete, refSK, false)
	if err != nil {
		return nil, err
	}
	if program == nil {
		return nil, fmt.Errorf("Program item not found at %s. Data inconsistency: pointer exists but program item missing.", refSK)
	}
	if !published(program) {
		return nil, notFound("Program version is unpublished: %s", refSK)
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
	return &Loaded{Program: program, SK: refSK, Version: version}, nil
}

func (p Programs) rebuildPointer(ctx context.Context, athlete string) (Item, error) {
	items, err := p.ListVersions(ctx, athlete, false)
	if err != nil {
		return nil, err
	}
	latest, latestSK := 0, ""
	for _, item := range items {
		if !published(item) {
			continue
		}
		sk := pyval.Str(item["sk"])
		if !strings.HasPrefix(sk, ProgramPrefix) {
			continue
		}
		token, _, _ := strings.Cut(strings.TrimPrefix(sk, ProgramPrefix), "-")
		number, err := strconv.Atoi(token)
		if err != nil {
			continue
		}
		if number > latest {
			latest, latestSK = number, sk
		}
	}
	if latestSK == "" {
		return nil, notFound("No program or pointer found for pk=%s. Create a program using new_version() first.", athlete)
	}
	pointer := Item{"pk": athlete, "sk": PointerSK, "version": int64(latest), "ref_sk": latestSK, "updated_at": p.Env.Stamp()}
	if err := p.DB.Put(ctx, p.Tables.Health, pointer); err != nil {
		return nil, err
	}
	return pointer, nil
}

type Snapshot struct {
	Program map[string]any
	SK      string
}

func (p Programs) Snapshot(ctx context.Context, athlete, selected string) (*Snapshot, error) {
	pointer, err := p.getHealth(ctx, athlete, PointerSK, true)
	if err != nil {
		return nil, err
	}
	if unselected(selected) {
		selected = pyval.Str2(pointer["ref_sk"])
	}
	if selected == "" {
		if selected, err = p.CurrentSK(ctx, athlete, ""); err != nil {
			return nil, err
		}
	}
	program, err := p.getHealth(ctx, athlete, selected, true)
	if err != nil {
		return nil, err
	}
	if program == nil {
		return nil, notFound("Program not found: %s", selected)
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
	if err := p.DB.Put(ctx, p.Tables.Health, updated); err != nil {
		return "", err
	}
	return now, nil
}

type Written struct {
	Program map[string]any
	SK      string
}

func (p Programs) WriteNewVersion(ctx context.Context, athlete string, program map[string]any, minor bool) (*Written, error) {
	now := p.Env.Stamp()
	pointer, err := p.getHealth(ctx, athlete, PointerSK, false)
	if err != nil {
		return nil, err
	}
	currentVersion := 0
	if pointer != nil {
		currentVersion = pyval.Int(pointer["version"], 0)
	}
	newVersion := currentVersion + 1
	meta, ok := program["meta"].(map[string]any)
	if !ok {
		meta = map[string]any{}
		program["meta"] = meta
	}
	label := "0.0"
	if value, present := meta["version_label"]; present {
		label = pyval.Str(value)
	}
	meta["version_label"] = nextLabel(label, minor, currentVersion, newVersion)
	meta["updated_at"] = now
	newSK := fmt.Sprintf("%s%03d-%s", ProgramPrefix, newVersion, p.Env.Hex())
	sessions, _ := pyval.DeepCopy(program["sessions"]).([]any)
	if err := ValidateIdentities(sessions); err != nil {
		return nil, err
	}
	item := pyval.CopyMap(program)
	delete(item, "sessions")
	item["pk"] = athlete
	item["sk"] = newSK
	item["published"] = true
	if err := p.DB.Put(ctx, p.Tables.Health, item); err != nil {
		return nil, err
	}
	phases, _ := program["phases"].([]any)
	if err := p.Sessions.WriteFresh(ctx, athlete, newSK, sessions, phases); err != nil {
		return nil, err
	}
	pointerItem := Item{"pk": athlete, "sk": PointerSK, "version": int64(newVersion), "ref_sk": newSK, "updated_at": now, "current_block_id": scope.CurrentBlockID(program)}
	if err := p.DB.Put(ctx, p.Tables.Health, pointerItem); err != nil {
		return nil, err
	}
	return &Written{Program: program, SK: newSK}, nil
}

func nextLabel(label string, minor bool, currentVersion, newVersion int) string {
	parts := strings.Split(label, ".")
	if len(parts) == 2 {
		major, errMajor := strconv.Atoi(strings.TrimSpace(parts[0]))
		minorNumber, errMinor := strconv.Atoi(strings.TrimSpace(parts[1]))
		if errMajor == nil && errMinor == nil {
			if minor {
				return fmt.Sprintf("%d.%d", major, minorNumber+1)
			}
			return fmt.Sprintf("%d.0", major+1)
		}
	}
	if currentVersion == 0 {
		return "1.0"
	}
	return fmt.Sprintf("%d.0", newVersion)
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
		if program != nil && published(program) {
			return ref, true, nil
		}
	}
	items, err := p.ListVersions(ctx, athlete, true)
	if err != nil {
		return "", false, err
	}
	for _, item := range items {
		if published(item) {
			return pyval.Str(item["sk"]), true, nil
		}
	}
	return "", false, nil
}

func (p Programs) WriteInitial(ctx context.Context, athlete string, program map[string]any) (string, error) {
	sk := ProgramPrefix + "001-" + p.Env.Hex()
	item := pyval.CopyMap(program)
	sessions, _ := item["sessions"].([]any)
	delete(item, "sessions")
	item["sk"] = sk
	item["published"] = true
	if err := p.DB.Put(ctx, p.Tables.Health, item); err != nil {
		return "", err
	}
	if len(sessions) > 0 {
		phases, _ := program["phases"].([]any)
		if err := p.Sessions.WriteFresh(ctx, athlete, sk, sessions, phases); err != nil {
			return "", err
		}
	}
	pointer := Item{"pk": athlete, "sk": PointerSK, "version": int64(1), "ref_sk": sk, "updated_at": p.Env.Stamp()}
	return sk, p.DB.Put(ctx, p.Tables.Health, pointer)
}

func (p Programs) VersionSK(ctx context.Context, athlete, version string) (string, error) {
	if version != "current" {
		return "program#" + version, nil
	}
	pointer, err := p.getHealth(ctx, athlete, PointerSK, false)
	if err != nil {
		return "", err
	}
	if pointer == nil {
		return "program#v001", nil
	}
	return pyOrDefault(pointer["ref_sk"], "program#v001"), nil
}

func (p Programs) BlockNotes(ctx context.Context, athlete, version string) (string, Item, error) {
	sk, err := p.VersionSK(ctx, athlete, version)
	if err != nil {
		return "", nil, err
	}
	item, err := p.DB.Get(ctx, p.Tables.Health, Key{PK: athlete, SK: sk}, GetOptions{Projection: []string{"meta.block_notes", "block_notes"}})
	return sk, item, err
}

func pyOrDefault(value any, fallback string) string {
	if value == nil {
		return fallback
	}
	return pyval.Str(value)
}
