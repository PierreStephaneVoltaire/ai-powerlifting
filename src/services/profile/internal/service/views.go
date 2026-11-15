package service

import (
	"context"

	"powerlifting/profile/internal/views"
)

func (s *Service) newViews() *views.Views {
	return &views.Views{DB: s.deps.DB, People: s.people, Access: s.access, Tags: s.tags, Env: s.deps.Env}
}

func (s *Service) registerViews() {
	v := s.newViews()
	s.handlers["profile_get"] = func(ctx context.Context, req *Request) (any, error) {
		return v.GetByHandle(ctx, text(req.Args, "nickname"), req.Caller.Person)
	}
	s.handlers["profile_get_current"] = func(ctx context.Context, req *Request) (any, error) {
		return v.GetCurrent(ctx, req.PK(), req.Caller.Person)
	}
	s.handlers["profile_search"] = func(ctx context.Context, req *Request) (any, error) {
		return v.Search(ctx, views.SearchArgs{
			Query:       text(req.Args, "query"),
			Federations: stringList(req.Args["federations"]),
			Tags:        stringList(req.Args["tags"]),
			Mode:        text(req.Args, "tag_mode"),
			Role:        text(req.Args, "role"),
			Cursor:      text(req.Args, "cursor"),
		}, req.Caller.Person)
	}
	s.handlers["profile_media_resolve"] = func(ctx context.Context, req *Request) (any, error) {
		return v.ResolveAvatar(ctx, req.PK(), req.Caller.Person, text(req.Args, "s3_key"))
	}
}

func (s *Service) registerHandlerContext() {
	v := s.newViews()
	s.handlers["handler_context"] = func(ctx context.Context, req *Request) (any, error) {
		return v.HandlerContext(ctx, req.PK(), req.Caller.Person, req.Access, s.deps.Analytics)
	}
}
