package service

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"slices"
	"sort"
	"time"

	"powerlifting/weight-log/internal/apperr"
	"powerlifting/weight-log/internal/auth"
	"powerlifting/weight-log/internal/contract"
	"powerlifting/weight-log/internal/store"
)

type Accessor interface {
	Fetch(context.Context, string, map[string]any, auth.Caller) (map[string]any, error)
}
type Storage interface {
	Get(context.Context, string, string) (map[string]any, error)
	Put(context.Context, map[string]any, string) error
}
type Versions interface {
	Bump(context.Context, string) error
}
type Service struct {
	Registry *contract.Registry
	Access   Accessor
	Store    Storage
	Versions Versions
	Now      func() time.Time
	Log      *slog.Logger
}

func New(registry *contract.Registry, access Accessor, storage Storage, versions Versions, log *slog.Logger) *Service {
	return &Service{Registry: registry, Access: access, Store: storage, Versions: versions, Log: log, Now: time.Now}
}
func (s *Service) Call(ctx context.Context, name string, args map[string]any, caller auth.Caller) (any, error) {
	if caller.Generation != nil && caller.ActiveJob() == "" {
		return nil, apperr.GenerationWithoutTurn()
	}
	op, ok := s.Registry.Get(name)
	if !ok {
		return nil, apperr.UnknownOperation()
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
	result, err := s.log(ctx, name, scoped)
	if err != nil {
		return nil, err
	}
	if err = op.ValidateResult(result); err != nil {
		return nil, apperr.InvalidResult()
	}
	if name != "weight_log_get" {
		athlete := auth.AnalysisAthlete(access)
		if athlete != "" {
			if err := s.Versions.Bump(ctx, athlete); err != nil {
				s.Log.Error("analysis version bump failed", "error", err)
			}
		}
	}
	if caller.Nested || caller.ActiveJob() == "" {
		return result, nil
	}
	return map[string]any{"status": "succeeded", "result": result}, nil
}
func (s *Service) log(ctx context.Context, name string, args map[string]any) (map[string]any, error) {
	pk := text(args["pk"])
	version := text(args["version"])
	if version == "" {
		version = "current"
	}
	sk := "weight_log#" + version
	log, err := s.Store.Get(ctx, pk, sk)
	if err != nil {
		return nil, err
	}
	if log == nil {
		log = map[string]any{"pk": pk, "sk": sk, "version": version, "entries": []any{}, "updated_at": s.Now().UTC().Format(time.RFC3339Nano)}
	}
	pointer, err := s.Store.Get(ctx, pk, "program#current")
	if err != nil {
		return nil, err
	}
	program := pointer
	if ref := text(pointer["ref_sk"]); ref != "" {
		program, err = s.Store.Get(ctx, pk, ref)
		if err != nil {
			return nil, err
		}
	}
	programActive, blocks := blockState(program)
	active := text(pointer["current_block_id"])
	if active == "" || active == "current" {
		active = programActive
	}
	entries, _ := log["entries"].([]any)
	if name != "weight_log_get" {
		previous := text(log["updated_at"])
		var entry map[string]any
		date := text(args["date"])
		if name == "weight_log_add" {
			entry, _ = args["entry"].(map[string]any)
			if len(entry) == 0 {
				entry = map[string]any{"date": date, "kg": args["weight_kg"]}
			} else {
				copy := map[string]any{}
				for k, v := range entry {
					copy[k] = v
				}
				entry = copy
				if _, ok := entry["kg"]; !ok {
					entry["kg"] = entry["weight_kg"]
					delete(entry, "weight_kg")
				}
			}
			date = text(entry["date"])
		}
		kept := make([]any, 0, len(entries)+1)
		for _, raw := range entries {
			item, ok := raw.(map[string]any)
			if !ok || belongs(item, programActive, blocks) != active || text(item["date"]) != date {
				kept = append(kept, raw)
			}
		}
		if entry != nil {
			if text(entry["block_id"]) == "" {
				entry["block_id"] = active
			}
			kept = append(kept, entry)
			sort.SliceStable(kept, func(i, j int) bool {
				a, _ := kept[i].(map[string]any)
				b, _ := kept[j].(map[string]any)
				return text(a["date"]) > text(b["date"])
			})
		}
		entries = kept
		log["entries"], log["version"], log["updated_at"] = entries, version, s.Now().UTC().Format(time.RFC3339Nano)
		if err = s.Store.Put(ctx, log, previous); err != nil {
			if errors.Is(err, store.ErrConflict) {
				return nil, &apperr.Error{Status: http.StatusConflict, Code: "concurrent_update", Message: err.Error()}
			}
			return nil, err
		}
	}
	target := text(args["block_id"])
	if len(program) == 0 {
		programActive = active
	}
	if target == "" {
		target = active
	}
	if target == "current" {
		target = programActive
	}
	if target != "all" {
		filtered := []any{}
		for _, raw := range entries {
			if entry, ok := raw.(map[string]any); ok && belongs(entry, programActive, blocks) == target {
				filtered = append(filtered, entry)
			}
		}
		log["entries"] = filtered
	}
	return log, nil
}
