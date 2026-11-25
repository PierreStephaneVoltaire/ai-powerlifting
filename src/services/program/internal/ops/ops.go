package ops

import (
	"context"
	"errors"
	"log/slog"

	"powerlifting/program/internal/apperr"
	"powerlifting/program/internal/env"
	"powerlifting/program/internal/pyval"
	"powerlifting/program/internal/store"
)

type Analytics interface {
	WeeklyAnalysis(ctx context.Context, caller Caller, arguments map[string]any) (*Weekly, error)
}

type Caller struct {
	Person    string
	Athlete   string
	ActiveJob string
}

type Config struct {
	TemplatesLibraryPK string
}

type Deps struct {
	Programs  store.Programs
	Related   store.Related
	Analytics Analytics
	Env       env.Env
	Config    Config
	Log       *slog.Logger
	Today     func() string
}

type Request struct {
	Ctx     context.Context
	Athlete string
	Person  string
	Args    map[string]any
	Access  map[string]any
	Caller  Caller
}

type Handler func(deps *Deps, request *Request) (any, error)

func (r *Request) String(key string) string {
	text, _ := r.Args[key].(string)
	return text
}

func (r *Request) Bool(key string) bool {
	return pyval.Truthy(r.Args[key])
}

func (r *Request) Selected() string {
	return r.String("program_sk")
}

func validation(message string) error {
	return apperr.Validation(message)
}

func mapError(err error) error {
	if err == nil {
		return nil
	}
	if _, ok := err.(*apperr.Error); ok {
		return err
	}
	if store.IsNotFound(err) {
		return apperr.NotFound("%s", err.Error())
	}
	var conflict *store.IdentityConflictError
	if errors.As(err, &conflict) {
		return apperr.Conflict("session_identity_conflict", conflict.Error())
	}
	if err == store.ErrSessionDate {
		return validation(err.Error())
	}
	return err
}

func Registry() map[string]Handler {
	return map[string]Handler{
		"program_get":                     programGet,
		"program_list_full":               programListFull,
		"program_archive":                 programArchive,
		"program_unarchive":               programUnarchive,
		"program_update_meta_field":       programUpdateMeta,
		"program_update_phases":           programUpdatePhases,
		"block_notes_get":                 blockNotesGet,
		"block_notes_update":              blockNotesUpdate,
		"diet_notes_update":               dietNotesUpdate,
		"supplement_phases_update":        supplementPhasesUpdate,
		"health_get_diet_notes":           getDietNotes,
		"health_get_supplements":          getSupplements,
		"health_invalidate_program_cache": invalidateCache,
		"health_new_version":              newVersion,
		"health_setup_status":             setupStatus,
		"health_setup_initialize":         setupInitialize,
		"block_transition":                blockTransition,
		"template_apply_sessions":         templateApplySessions,
		"program_apply_session_import":    programApplySessionImport,
		"export_program_markdown":         exportMarkdown,
	}
}
