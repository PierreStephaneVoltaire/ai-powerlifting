package service

import (
	"context"
	"errors"
	"net/http"
	"slices"
	"strings"
	"time"

	"powerlifting/templates/internal/apperr"
	"powerlifting/templates/internal/apply"
	"powerlifting/templates/internal/auth"
	"powerlifting/templates/internal/coach"
	"powerlifting/templates/internal/contract"
	"powerlifting/templates/internal/execution"
	"powerlifting/templates/internal/library"
	"powerlifting/templates/internal/patch"
	"powerlifting/templates/internal/payload"
)

type Accessor interface {
	Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error)
}
type Domain interface {
	Call(context.Context, string, string, map[string]any, auth.Caller) (map[string]any, error)
}
type ClaimVerifier interface {
	VerifyClaim(context.Context, library.ImportClaim) (bool, error)
}
type Sources interface {
	ProgramContext(context.Context, string) (map[string]any, error)
	Program(context.Context, string, string) (map[string]any, error)
	Glossary(context.Context, string) ([]map[string]any, error)
}
type Service struct {
	Domain     Domain
	Sources    Sources
	Coach      coach.Client
	Executions *execution.Manager
	Claims     ClaimVerifier
	Registry   *contract.Registry
	Access     Accessor
	Library    library.Library
}

func value(v any) string { s, _ := v.(string); return s }
func defaultValue(v any, fallback any) any {
	if v == nil {
		return fallback
	}
	return v
}
func (s *Service) Call(ctx context.Context, name string, args map[string]any, caller auth.Caller) (any, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return nil, apperr.GenerationWithoutTurn()
	}
	op, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
	}
	if name == "template_create_from_import" && auth.ServiceAccount(caller.Source) != "pl-imports" {
		return nil, apperr.Forbidden("Operation is restricted to the imports workload")
	}
	for key := range args {
		if slices.Contains([]string{"_person_pk", "_access", "_if_job_id"}, key) {
			return nil, apperr.Forbidden("Reserved authorization fields cannot be supplied")
		}
	}
	access, err := s.Access.Fetch(ctx, name, args, caller)
	if err != nil {
		return nil, err
	}
	if op.InternalOnly && !caller.IsBackend() {
		return nil, apperr.Forbidden("Operation is internal to the gateway")
	}
	scoped, err := auth.Scope(op, args, caller, access)
	if err != nil {
		return nil, err
	}
	if err = op.ValidateInput(scoped); err != nil {
		return nil, apperr.Validation(err.Error())
	}
	if caller.Nested && caller.ActiveJob() == "" {
		return nil, apperr.NestedWithoutExecution()
	}
	owners := []string{caller.Person}
	for _, k := range []string{"settings_pk", "own_athlete_pk"} {
		if alias := value(access[k]); alias != "" && !slices.Contains(owners, alias) {
			owners = append(owners, alias)
		}
	}
	if name == "template_evaluate" {
		return s.evaluate(ctx, scoped, caller, owners, op)
	}
	result, err := s.call(ctx, name, scoped, caller, owners)
	if err != nil {
		if errors.Is(err, library.ErrNotFound) {
			return nil, apperr.NotFound("Template not found: %s", value(scoped["sk"]))
		}
		if errors.Is(err, library.ErrValidation) {
			return nil, apperr.Validation(err.Error())
		}
		if errors.Is(err, library.ErrForbidden) {
			return nil, apperr.Forbidden(err.Error())
		}
		return nil, err
	}
	if err = op.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}
func (s *Service) call(ctx context.Context, name string, args map[string]any, caller auth.Caller, owners []string) (any, error) {
	actor := caller.Person
	sk := value(args["sk"])
	switch name {
	case "template_list":
		archived, _ := args["include_archived"].(bool)
		return s.Library.List(ctx, owners, archived)
	case "template_get":
		item, err := s.Library.Get(ctx, sk, owners)
		if err != nil {
			return nil, err
		}
		meta, _ := item["meta"].(map[string]any)
		author := value(meta["author_pk"])
		item["is_owner"] = author != "" && slices.Contains(owners, author)
		return item, nil
	case "template_create_blank":
		meta := map[string]any{"name": args["name"], "description": defaultValue(args["description"], ""), "program_context": defaultValue(args["program_context"], ""), "estimated_weeks": defaultValue(args["estimated_weeks"], 4), "days_per_week": defaultValue(args["days_per_week"], 3), "archived": false}
		id, err := s.Library.Create(ctx, map[string]any{"meta": meta, "sessions": []any{}, "phases": []any{}}, actor, actor, false)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "created", "sk": id}, nil
	case "template_create_from_payload":
		input, _ := args["template"].(map[string]any)
		prepared, err := payload.Prepare(input, true)
		if err != nil {
			return nil, err
		}
		meta := prepared["meta"].(map[string]any)
		meta["name"] = payload.ImportedName(meta)
		if job := value(args["import_job_id"]); job != "" {
			meta["import_job_id"] = job
		}
		published, _ := args["published"].(bool)
		id, err := s.Library.Create(ctx, prepared, actor, value(args["author"]), published)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "created", "sk": id}, nil
	case "template_create_from_import":
		if s.Claims == nil {
			return nil, apperr.Upstream("Import claim verification unavailable")
		}
		claim := library.ImportClaim{Athlete: value(args["pk"]), ImportID: value(args["import_id"]), ClaimID: value(args["claim_id"])}
		valid, err := s.Claims.VerifyClaim(ctx, claim)
		if err != nil {
			return nil, apperr.Upstream("Import claim verification unavailable")
		}
		if !valid {
			return nil, apperr.Forbidden("Import claim is not active")
		}
		input, _ := args["template"].(map[string]any)
		prepared, err := payload.Prepare(input, true)
		if err != nil {
			return nil, err
		}
		meta := prepared["meta"].(map[string]any)
		meta["name"], meta["import_job_id"], meta["published"] = payload.ImportedName(meta), claim.ImportID, false
		id, err := s.Library.CreateImport(ctx, prepared, actor, value(args["author"]), claim)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "created", "sk": id}, nil
	case "template_create_from_block":
		if s.Sources == nil {
			return nil, apperr.Upstream("Program source unavailable")
		}
		program, err := s.Sources.Program(ctx, caller.Athlete, value(args["program_sk"]))
		if err != nil {
			return nil, apperr.Upstream("Program service unavailable")
		}
		maxes, _ := program["current_maxes"].(map[string]any)
		converted, err := apply.Convert(program, maxes)
		if err != nil {
			return nil, apperr.Validation(err.Error())
		}
		converted["meta"].(map[string]any)["name"] = args["name"]
		id, err := s.Library.Create(ctx, converted, actor, value(args["author"]), false)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "created", "sk": id}, nil
	case "template_apply":
		template, err := s.Library.Get(ctx, sk, owners)
		if err != nil {
			return nil, err
		}
		if s.Sources == nil {
			return nil, apperr.Upstream("Sources unavailable")
		}
		program, err := s.Sources.ProgramContext(ctx, caller.Athlete)
		if err != nil {
			return nil, apperr.Upstream("Program service unavailable")
		}
		entries, err := s.Sources.Glossary(ctx, caller.Athlete)
		if err != nil {
			return nil, apperr.Upstream("Glossary service unavailable")
		}
		maxes, _ := program["current_maxes"].(map[string]any)
		target := defaultValue(args["target"], "new_block")
		weekDay := "Monday"
		inputDay := value(args["week_start_day"])
		for _, day := range []string{"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"} {
			if strings.EqualFold(strings.TrimSpace(inputDay), day) {
				weekDay = day
				break
			}
		}
		missing := apply.Missing(template, maxes, entries)
		if len(missing) > 0 {
			return map[string]any{"status": "gate_blocked", "missing_exercises": missing, "missing_maxes": missing, "target": target, "start_date": args["start_date"], "week_start_day": weekDay}, nil
		}
		start := time.Now()
		if date := value(args["start_date"]); date != "" {
			start, err = time.Parse("2006-01-02", date)
			if err != nil {
				return nil, apperr.Validation("Invalid start date")
			}
		}
		sessions, err := apply.Concretize(template, maxes, entries, start, weekDay)
		if err != nil {
			return nil, apperr.Validation(err.Error())
		}
		if len(sessions) > 5 {
			sessions = sessions[:5]
		}
		return map[string]any{"status": "ready", "preview_sessions": sessions, "target": target, "start_date": start.Format("2006-01-02"), "week_start_day": weekDay, "block_id": args["block_id"], "block_name": args["block_name"]}, nil
	case "template_copy":
		id, err := s.Library.Copy(ctx, sk, value(args["new_name"]), actor, value(args["author"]), owners)
		if err != nil {
			return nil, err
		}
		return map[string]any{"status": "copied", "new_sk": id}, nil
	case "template_apply_confirm":
		target := value(args["target"])
		if target == "" || target == "new_block" {
			return s.confirmNewBlock(ctx, args, caller, owners)
		}
		return nil, apperr.Uncertain("This template target cannot safely commit while concurrent session writes are unversioned")
	case "template_update":
		input, _ := args["template"].(map[string]any)
		if err := s.Library.Update(ctx, sk, input, owners); err != nil {
			return nil, err
		}
		return map[string]any{"status": "updated", "sk": sk}, nil
	case "template_report":
		return s.report(ctx, sk, args, caller, owners)
	case "template_patch":
		template, err := s.Library.Get(ctx, sk, owners)
		if err != nil {
			return nil, err
		}
		operations, _ := args["operations"].([]any)
		entries := []map[string]any{}
		for _, raw := range operations {
			op, _ := raw.(map[string]any)
			if value(op["op"]) == "set_session_weekdays" {
				continue
			}
			if s.Sources == nil {
				return nil, apperr.Upstream("Glossary service unavailable")
			}
			entries, err = s.Sources.Glossary(ctx, caller.Athlete)
			if err != nil {
				return nil, apperr.Upstream("Glossary service unavailable")
			}
			break
		}
		updated, changes, unmatched, err := patch.Apply(template, operations, entries)
		if err != nil {
			return nil, apperr.Validation(err.Error())
		}
		hash, err := patch.Hash(sk, operations)
		if err != nil {
			return nil, err
		}
		requested, _ := args["apply"].(bool)
		applied := requested && len(changes) > 0
		if applied {
			if err := s.Library.Update(ctx, sk, updated, owners); err != nil {
				return nil, err
			}
		}
		return map[string]any{"sk": sk, "applied": applied, "preview_hash": hash, "changes": changes, "unmatched": unmatched}, nil
	case "template_archive", "template_unarchive", "template_publish", "template_unpublish":
		field, enabled, status := "archived", name == "template_archive", "unarchived"
		if name == "template_archive" {
			status = "archived"
		}
		if name == "template_publish" || name == "template_unpublish" {
			field, enabled, status = "published", name == "template_publish", "unpublished"
			if enabled {
				status = "published"
			}
		}
		if err := s.Library.SetStatus(ctx, sk, owners, field, enabled); err != nil {
			return nil, err
		}
		return map[string]any{"status": status, "sk": sk}, nil
	case "template_delete":
		if err := s.Library.Delete(ctx, sk, owners); err != nil {
			return nil, err
		}
		return map[string]any{"status": "deleted", "sk": sk}, nil
	}
	return nil, &apperr.Error{Status: http.StatusNotImplemented, Code: "not_implemented", Message: "Template operation is not implemented"}
}
