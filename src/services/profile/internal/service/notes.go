package service

import (
	"context"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/notes"
)

func (s *Service) registerNotes() {
	store := &notes.Store{DB: s.deps.DB, Env: s.deps.Env}
	person := func(req *Request) (string, error) {
		if req.Caller.Person == "" {
			return "", apperr.Validation("Authenticated Person required")
		}
		return req.Caller.Person, nil
	}
	athlete := func(req *Request) (string, error) {
		if req.PK() == "" {
			return "", apperr.Validation("Athlete scope required")
		}
		return req.PK(), nil
	}
	s.handlers["note_list_private"] = func(ctx context.Context, req *Request) (any, error) {
		who, err := person(req)
		if err != nil {
			return nil, err
		}
		return store.ListPrivate(ctx, who)
	}
	s.handlers["note_save_private"] = func(ctx context.Context, req *Request) (any, error) {
		who, err := person(req)
		if err != nil {
			return nil, err
		}
		note, err := store.SavePrivate(ctx, who, req.Args)
		if err != nil {
			return nil, err
		}
		return map[string]any{"note": note}, nil
	}
	s.handlers["note_list_attachments"] = func(ctx context.Context, req *Request) (any, error) {
		owner, err := athlete(req)
		if err != nil {
			return nil, err
		}
		return store.ListAttachments(ctx, owner, req.Args, req.Access)
	}
	s.handlers["note_share"] = func(ctx context.Context, req *Request) (any, error) {
		owner, err := athlete(req)
		if err != nil {
			return nil, err
		}
		who, err := person(req)
		if err != nil {
			return nil, err
		}
		return store.Share(ctx, owner, who, req.Args, req.Access)
	}
	s.handlers["note_detach"] = func(ctx context.Context, req *Request) (any, error) {
		owner, err := athlete(req)
		if err != nil {
			return nil, err
		}
		return store.Detach(ctx, owner, req.Args, req.Access)
	}
}
