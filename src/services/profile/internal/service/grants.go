package service

import (
	"context"
	"regexp"
	"strings"
	"time"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

var mappedPK = regexp.MustCompile(`^[A-Za-z0-9:_#-]{1,128}$`)

func (s *Service) registerGrants() {
	s.handlers["grant_check"] = s.grantCheck
	s.handlers["grant_list"] = s.grantList
	s.handlers["grant_create"] = func(context.Context, *Request) (any, error) {
		return nil, apperr.Validation("direct_grant_creation_retired_use_relationship_request")
	}
	s.handlers["grant_revoke"] = func(context.Context, *Request) (any, error) {
		return nil, apperr.Validation("direct_grant_revocation_retired_use_relationship_revoke")
	}
}

func str(item value.Item, key string) string { return value.Str(value.Or(item[key], "")) }

func list(item value.Item, key string) []any {
	if entries, ok := item[key].([]any); ok && len(entries) > 0 {
		return entries
	}
	return []any{}
}

func normalizeGrant(item value.Item) map[string]any {
	dates := map[string]any{}
	if raw, ok := item["tied_competition_dates"].(map[string]any); ok {
		dates = raw
	}
	scope := str(item, "scope")
	if scope == "" {
		scope = "read"
	}
	state := str(item, "state")
	if state == "" {
		state = "approved"
	}
	entity := str(item, "entity")
	if entity == "" {
		entity = "grant"
	}
	return map[string]any{
		"pk": item["pk"], "sk": item["sk"],
		"athlete_mapped_pk": str(item, "athlete_mapped_pk"), "athlete_nickname": str(item, "athlete_nickname"),
		"grantee_mapped_pk": str(item, "grantee_mapped_pk"), "grantee_nickname": str(item, "grantee_nickname"),
		"grantee_discord_id": str(item, "grantee_discord_id"), "grantee_authentik_sub": str(item, "grantee_authentik_sub"),
		"grant_type": str(item, "grant_type"), "scope": scope,
		"tied_competition_ids": list(item, "tied_competition_ids"),
		"expires_at":           str(item, "expires_at"),
		"revoked_at":           item["revoked_at"], "revoked_by": item["revoked_by"],
		"created_by": str(item, "created_by"), "note": str(item, "note"), "last_edited_by": str(item, "last_edited_by"),
		"created_at": str(item, "created_at"), "updated_at": str(item, "updated_at"),
		"entity": entity, "state": state,
		"relationship_id": str(item, "relationship_id"), "athlete_person_pk": str(item, "athlete_person_pk"),
		"grantee_person_pk":      str(item, "grantee_person_pk"),
		"permissions":            list(item, "permissions"),
		"tied_competition_dates": dates,
	}
}

func grantActive(grant map[string]any, now time.Time) bool {
	if value.Truthy(grant["revoked_at"]) {
		return false
	}
	expires := value.Str(grant["expires_at"])
	if expires == "" {
		return false
	}
	parsed, _, ok := clock.ParseISO(expires)
	return ok && parsed.After(now)
}

func (s *Service) grantRows(ctx context.Context, athlete string) ([]map[string]any, error) {
	rows, err := s.deps.DB.Query(ctx, store.Query{
		Table:   s.deps.DB.Tables.Requests,
		KeyCond: "pk = :pk",
		Values:  map[string]any{":pk": "Grant#" + athlete},
	})
	if err != nil {
		return nil, err
	}
	out := make([]map[string]any, len(rows))
	for i, row := range rows {
		out[i] = normalizeGrant(row)
	}
	return out, nil
}

func trimmed(arguments map[string]any, key string) string {
	return strings.TrimSpace(value.Str(value.Or(arguments[key], "")))
}

func (s *Service) grantCheck(ctx context.Context, req *Request) (any, error) {
	athlete, actor := trimmed(req.Args, "athlete_mapped_pk"), trimmed(req.Args, "actor_mapped_pk")
	grantType, scope, tied := trimmed(req.Args, "grant_type"), trimmed(req.Args, "scope"), trimmed(req.Args, "tied_competition_id")
	if !mappedPK.MatchString(athlete) {
		return nil, apperr.Validation("invalid_athlete_mapped_pk")
	}
	if !mappedPK.MatchString(actor) {
		return nil, apperr.Validation("invalid_actor_mapped_pk")
	}
	if athlete == actor {
		return map[string]any{"allowed": true, "reason": "self"}, nil
	}
	rows, err := s.grantRows(ctx, athlete)
	if err != nil {
		return nil, err
	}
	now := s.deps.Env.Now()
	for _, row := range rows {
		if !grantActive(row, now) || row["grantee_mapped_pk"] != actor {
			continue
		}
		if grantType != "" && row["grant_type"] != grantType {
			continue
		}
		if scope == "write" && row["scope"] != "write" {
			continue
		}
		if tied != "" {
			ids := stringList(row["tied_competition_ids"])
			if len(ids) > 0 && !containsString(ids, tied) {
				continue
			}
		}
		return map[string]any{"allowed": true, "grant": row, "reason": "active_grant"}, nil
	}
	return map[string]any{"allowed": false, "reason": "no_active_grant"}, nil
}

func (s *Service) grantList(ctx context.Context, req *Request) (any, error) {
	athlete, grantee := trimmed(req.Args, "athlete_mapped_pk"), trimmed(req.Args, "grantee_mapped_pk")
	if athlete != "" && !mappedPK.MatchString(athlete) {
		return nil, apperr.Validation("invalid_athlete_mapped_pk")
	}
	if grantee != "" && !mappedPK.MatchString(grantee) {
		return nil, apperr.Validation("invalid_grantee_mapped_pk")
	}
	if athlete == "" && grantee == "" {
		return nil, apperr.Validation("athlete_or_grantee_required")
	}
	var rows []map[string]any
	if athlete != "" {
		all, err := s.grantRows(ctx, athlete)
		if err != nil {
			return nil, err
		}
		for _, row := range all {
			if grantee == "" || row["grantee_mapped_pk"] == grantee {
				rows = append(rows, row)
			}
		}
	} else {
		scanned, err := s.deps.DB.Scan(ctx, store.Scan{Table: s.deps.DB.Tables.Requests})
		if err != nil {
			return nil, err
		}
		for _, item := range scanned {
			if row := normalizeGrant(item); row["grantee_mapped_pk"] == grantee {
				rows = append(rows, row)
			}
		}
	}
	now := s.deps.Env.Now()
	active, inactive := []any{}, []any{}
	for _, row := range rows {
		if grantActive(row, now) {
			active = append(active, row)
		} else {
			inactive = append(inactive, row)
		}
	}
	if req.Args["include_inactive"] != true && !value.Truthy(req.Args["include_inactive"]) {
		return map[string]any{"active": active, "total": len(active), "inactive": []any{}}, nil
	}
	return map[string]any{"active": active, "inactive": inactive, "total": len(rows)}, nil
}
