package service

import (
	"context"

	"powerlifting/analytics-ai/internal/apperr"
	"powerlifting/analytics-ai/internal/auth"
	"powerlifting/analytics-ai/internal/generation"
)

const startingGrace = 60

func (s *Service) GenerationStatus(ctx context.Context, id string, caller auth.Caller) (map[string]any, error) {
	if caller.Athlete == "" {
		return nil, apperr.Forbidden("Authenticated Athlete required")
	}
	access, err := s.Access.Fetch(ctx, "generation_status", map[string]any{}, caller)
	if err != nil {
		return nil, err
	}
	store := s.store(caller.Athlete)
	record, err := store.Get(ctx, id)
	if err != nil {
		return nil, err
	}
	if record == nil {
		return nil, apperr.NotFound("Report generation not found")
	}
	if err := generation.AuthorizeSource(record.Requirements, access); err != nil {
		return nil, apperr.Forbidden(err.Error())
	}
	switch {
	case caller.Person != "" && !generation.Terminal(record.Status) && record.JobID != "":
		job, err := s.Coach.Status(ctx, caller.Person, caller.Athlete, record.JobID)
		if err != nil {
			return nil, err
		}
		if generation.Terminal(job.Status) {
			if record, err = store.Get(ctx, id); err != nil {
				return nil, err
			}
			if record.Status == generation.StatusDone {
				result, err := s.cachedResult(ctx, report{id: id, store: store}, record)
				if err != nil {
					return nil, err
				}
				return map[string]any{"generation_id": id, "status": generation.StatusDone, "cached": true, "result": result}, nil
			}
			record.Status = job.Status
			if job.Status == generation.StatusDone {
				record.Status = "uncertain"
			}
			record.Error = job.Error
			if record.Error == nil {
				record.Error = map[string]any{"message": "Report did not persist a validated result; explicitly retry"}
			}
			if err := store.Update(ctx, id, record.Attempt, generation.Item{"status": record.Status, "error": record.Error}); err != nil {
				return nil, err
			}
		}
	case record.Status == "starting" && record.JobID == "" && s.Now().Unix()-record.UpdatedAt > startingGrace:
		record.Status = "uncertain"
		if err := store.Update(ctx, id, record.Attempt, generation.Item{"status": "uncertain"}); err != nil {
			return nil, err
		}
	}
	result := map[string]any{"generation_id": id, "status": record.Status, "source_fingerprint": record.Fingerprint, "job_id": nullable(record.JobID), "error": record.Error}
	if record.Status == generation.StatusDone {
		stored, err := s.cachedResult(ctx, report{id: id, store: store}, record)
		if err != nil {
			return nil, err
		}
		result["result"], result["cached"] = stored, true
	}
	return result, nil
}
