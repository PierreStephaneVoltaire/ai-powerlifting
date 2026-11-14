package access

import (
	"context"
	"slices"
	"sort"
	"time"

	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

type Scope struct {
	Unrestricted bool
	IDs          []string
}

func (s Scope) add(ids []string) Scope {
	if s.Unrestricted {
		return s
	}
	for _, id := range ids {
		if !slices.Contains(s.IDs, id) {
			s.IDs = append(s.IDs, id)
		}
	}
	return s
}

func (s Scope) Covers(identifier string) bool {
	return s.Unrestricted || slices.Contains(s.IDs, identifier)
}

func (s Scope) value() any {
	if s.Unrestricted {
		return nil
	}
	ids := slices.Clone(s.IDs)
	sort.Strings(ids)
	out := make([]any, len(ids))
	for i, id := range ids {
		out[i] = id
	}
	return out
}

type Context struct {
	PersonPK           string
	AthletePK          string
	OwnAthletePK       string
	SettingsPK         string
	IsSelf             bool
	Permissions        []string
	GrantedPermissions []string
	ReadScope          Scope
	WriteScope         Scope
	DisplayName        string
	HasDisplayName     bool
	Sex                string
	Owner              value.Item
}

func (c *Context) Has(permission string) bool {
	return permission != "" && slices.Contains(c.Permissions, permission)
}

func (c *Context) Granted(permission string) bool {
	return slices.Contains(c.GrantedPermissions, permission)
}

func (c *Context) Scope(permission string) Scope {
	if permission == "competition:write" {
		return c.WriteScope
	}
	return c.ReadScope
}

func strList(values []string) []any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

func (c *Context) Map() map[string]any {
	out := map[string]any{
		"person_pk":           c.PersonPK,
		"athlete_pk":          c.AthletePK,
		"own_athlete_pk":      c.OwnAthletePK,
		"settings_pk":         c.SettingsPK,
		"is_self":             c.IsSelf,
		"permissions":         strList(c.Permissions),
		"granted_permissions": strList(c.GrantedPermissions),
		"competition_scope":   map[string]any{"read": c.ReadScope.value(), "write": c.WriteScope.value()},
	}
	if c.HasDisplayName {
		out["athlete_display_name"] = c.DisplayName
	}
	if c.Sex != "" {
		out["athlete_sex"] = c.Sex
	}
	return out
}

func text(item value.Item, key string) string {
	if item == nil || !value.Truthy(item[key]) {
		return ""
	}
	return value.Str(item[key])
}

func Evaluate(person, athlete string, owner, actor value.Item, grants []Grant, dates map[string]string, now time.Time) *Context {
	permissions := map[string]bool{"calculations:read": true, "federation:read": true}
	granted := map[string]bool{}
	ownAthlete := text(actor, "mapped_pk")
	if ownAthlete == "" {
		ownAthlete = text(actor, "pk")
	}
	isSelf := person != "" && len(actor) > 0 && len(owner) > 0 && ownAthlete == athlete
	ctx := &Context{PersonPK: person, AthletePK: athlete, OwnAthletePK: ownAthlete, SettingsPK: text(actor, "pk"), IsSelf: isSelf}
	if isSelf {
		ctx.ReadScope, ctx.WriteScope = Scope{Unrestricted: true}, Scope{Unrestricted: true}
	}
	if len(actor) > 0 {
		permissions["settings:read"], permissions["settings:write"] = true, true
	}
	if isSelf {
		permissions["profile:read"], permissions["profile:write"] = true, true
		if roles, _ := actor["roles"].([]any); slices.Contains(listStrings(roles), "athlete") {
			permissions["grants:read"], permissions["grants:write"] = true, true
			if people.DeriveOnboarding(actor).HasAthleteBasics {
				for _, permission := range CoachPermissions {
					permissions[permission] = true
				}
			}
		}
	}
	if owner != nil && owner["profile_visibility"] == "public" {
		permissions["profile:read"] = true
		publication, _ := owner["publication"].(map[string]any)
		domains, _ := publication["domains"].([]any)
		for _, entry := range domains {
			domain, _ := entry.(string)
			if isDomain(domain) {
				permissions[domain+":read"] = true
				if domain == "competition" {
					ctx.ReadScope = Scope{Unrestricted: true}
				}
			}
		}
	}
	if len(actor) > 0 {
		actorIDs := []string{person, text(actor, "pk"), ownAthlete}
		for _, grant := range ActiveGrants(grants, dates, now) {
			if !slices.Contains(actorIDs, grant.GranteeMappedPK) && grant.GranteePersonPK != person {
				continue
			}
			effective := GrantPermissions(grant, dates, now)
			for _, permission := range effective {
				granted[permission] = true
			}
			for _, action := range []string{"read", "write"} {
				if !slices.Contains(effective, "competition:"+action) {
					continue
				}
				scope := &ctx.ReadScope
				if action == "write" {
					scope = &ctx.WriteScope
				}
				if scope.Unrestricted {
					continue
				}
				if grant.Role == "peer" || grant.Role == "read" {
					*scope = Scope{Unrestricted: true}
				} else {
					*scope = scope.add(grant.Tied)
				}
			}
		}
		for permission := range granted {
			permissions[permission] = true
		}
	}
	if len(actor) > 0 && ownAthlete == "operator" {
		permissions["operator:read"], permissions["operator:write"] = true, true
	}
	ctx.Permissions = sortedKeys(permissions)
	ctx.GrantedPermissions = sortedKeys(granted)
	return ctx
}

func listStrings(values []any) []string {
	var out []string
	for _, v := range values {
		if s, ok := v.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for key := range set {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}

type Provider struct {
	People *people.Repo
	DB     *store.DB
	Now    func() time.Time
}

func (p *Provider) Context(ctx context.Context, person, athlete string) (*Context, error) {
	actor, err := p.People.Record(ctx, person)
	if err != nil {
		return nil, err
	}
	var owner value.Item
	if len(actor) > 0 && (athlete == text(actor, "pk") || (value.Truthy(actor["mapped_pk"]) && athlete == value.Str(actor["mapped_pk"]))) {
		owner = actor
	} else if owner, err = p.People.Record(ctx, athlete); err != nil {
		return nil, err
	}
	var grants []Grant
	dates := map[string]string{}
	if len(actor) > 0 && len(owner) > 0 && firstText(actor, "mapped_pk", "pk") != athlete {
		rows, err := p.DB.Query(ctx, store.Query{
			Table:      p.DB.Tables.Requests,
			KeyCond:    "pk = :pk",
			Values:     map[string]any{":pk": "Grant#" + athlete},
			Consistent: true,
		})
		if err != nil {
			return nil, err
		}
		for _, row := range rows {
			grants = append(grants, GrantOf(row))
		}
		if dates, err = p.CompetitionDates(ctx, athlete); err != nil {
			return nil, err
		}
	}
	evaluated := Evaluate(person, athlete, owner, actor, grants, dates, p.Now())
	evaluated.Owner = owner
	if len(owner) > 0 && evaluated.Has("profile:read") {
		evaluated.HasDisplayName = true
		evaluated.DisplayName = firstText(owner, "display_name", "nickname")
		if evaluated.DisplayName == "" {
			evaluated.DisplayName = athlete
		}
	}
	if len(owner) > 0 && evaluated.Has("performance:read") {
		if sex, _ := owner["sex"].(string); sex == "male" || sex == "female" {
			evaluated.Sex = sex
		}
	}
	return evaluated, nil
}

func firstText(item value.Item, keys ...string) string {
	for _, key := range keys {
		if v := text(item, key); v != "" {
			return v
		}
	}
	return ""
}

func (p *Provider) CompetitionDates(ctx context.Context, athlete string) (map[string]string, error) {
	rows, err := p.DB.Query(ctx, store.Query{
		Table:      p.DB.Tables.Competitions,
		KeyCond:    "pk = :pk AND begins_with(sk, :prefix)",
		Values:     map[string]any{":pk": athlete, ":prefix": "COMP#"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	dates := map[string]string{}
	for _, row := range rows {
		date, ok := value.Or(value.Or(row["date"], row["competition_date"]), row["start_date"]).(string)
		if !ok {
			continue
		}
		sk := value.Str(row["sk"])
		keys := []string{sk, ""}
		if len(sk) >= 5 {
			keys[1] = sk[5:]
		}
		for _, field := range []string{"competition_id", "master_id", "id"} {
			if value.Truthy(row[field]) {
				keys = append(keys, value.Str(row[field]))
			}
		}
		for _, key := range keys {
			if key != "" {
				dates[key] = date
			}
		}
	}
	return dates, nil
}
