package service

import "context"

func (s *Service) registerAccess() {
	s.handlers["access_context"] = func(_ context.Context, req *Request) (any, error) {
		return req.Access.Map(), nil
	}
}
