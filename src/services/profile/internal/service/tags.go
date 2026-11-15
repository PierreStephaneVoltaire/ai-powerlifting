package service

import (
	"context"

	"powerlifting/profile/internal/tags"
)

func (s *Service) registerTags() {
	s.handlers["tag_catalog_get"] = func(ctx context.Context, req *Request) (any, error) {
		return s.tags.Listing(ctx, req.Access.SettingsPK, req.Args["include_pending"] == true, req.Access.Has("operator:write"))
	}
	s.handlers["settings_tag_approve"] = func(ctx context.Context, req *Request) (any, error) {
		return s.tags.Decide(ctx, req.Access.Has("operator:write"), req.Caller.Person, text(req.Args, "tag"), text(req.Args, "decision"))
	}
	selection := func(remove bool) handler {
		return func(ctx context.Context, req *Request) (any, error) {
			return s.tags.Select(ctx, tags.Selection{
				Person:         req.Caller.Person,
				Athlete:        req.PK(),
				Tag:            text(req.Args, "tag"),
				TargetNickname: text(req.Args, "target_nickname"),
				Remove:         remove,
			}, req.Access.SettingsPK)
		}
	}
	s.handlers["settings_tag_add"] = selection(false)
	s.handlers["settings_tag_propose"] = selection(false)
	s.handlers["settings_tag_remove"] = selection(true)
}
