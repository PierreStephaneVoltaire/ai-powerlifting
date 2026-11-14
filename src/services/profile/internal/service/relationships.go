package service

import (
	"context"

	"powerlifting/profile/internal/relations"
)

func (s *Service) registerRelationships() {
	service := &relations.Service{DB: s.deps.DB, People: s.people, Access: s.access, Env: s.deps.Env}
	caller := func(req *Request) relations.Caller {
		return relations.Caller{Person: req.Caller.Person, Access: req.Access}
	}
	s.handlers["relationship_request"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Request(ctx, req.Args, caller(req))
	}
	s.handlers["relationship_respond"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Respond(ctx, req.Args, caller(req))
	}
	s.handlers["relationship_revoke"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Revoke(ctx, req.Args, caller(req))
	}
	s.handlers["relationship_list"] = func(ctx context.Context, req *Request) (any, error) {
		return service.List(ctx, caller(req))
	}
	s.handlers["relationship_history"] = func(ctx context.Context, req *Request) (any, error) {
		return service.History(ctx, caller(req))
	}
	s.handlers["favorite"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Favorite(ctx, req.Args, caller(req))
	}
	s.handlers["favorites"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Favorites(ctx, caller(req))
	}
	s.handlers["notifications"] = func(ctx context.Context, req *Request) (any, error) {
		return service.Notifications(ctx, caller(req))
	}
	s.handlers["notifications_read"] = func(ctx context.Context, req *Request) (any, error) {
		return service.MarkRead(ctx, req.Args, caller(req))
	}
}
