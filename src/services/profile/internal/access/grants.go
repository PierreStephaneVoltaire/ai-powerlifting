package access

import (
	"slices"
	"strings"
	"time"

	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/value"
)

var Domains = []string{"profile", "program", "sessions", "competition", "federation", "glossary", "goals", "budget", "calculations", "performance", "weight-log", "templates", "imports", "lift-profiles", "analytics", "videos"}

var handlerDomains = []string{"profile", "program", "sessions", "competition", "budget", "performance", "lift-profiles", "videos", "calculations"}

var (
	CoachPermissions   = domainPermissions(Domains, "read", "write")
	HandlerPermissions = append(domainPermissions(handlerDomains, "read"), "competition:write")
)

func domainPermissions(domains []string, actions ...string) []string {
	var out []string
	for _, domain := range domains {
		for _, action := range actions {
			out = append(out, domain+":"+action)
		}
	}
	return out
}

func isDomain(name string) bool { return slices.Contains(Domains, name) }

type Grant struct {
	SK              string
	Entity          string
	Role            string
	State           string
	StatePresent    bool
	Revoked         bool
	Tied            []string
	ExpiresAt       string
	Permissions     []string
	PermissionsSet  bool
	PermissionsList bool
	Scope           string
	RelationshipID  string
	GranteeMappedPK string
	GranteePersonPK string
}

func present(v any) string {
	if !value.Truthy(v) {
		return ""
	}
	return value.Str(v)
}

func GrantOf(item value.Item) Grant {
	grant := Grant{
		SK:              value.Str(orEmpty(item["sk"])),
		Entity:          present(item["entity"]),
		Role:            present(value.Or(item["grant_type"], item["kind"])),
		Revoked:         value.Truthy(item["revoked_at"]),
		ExpiresAt:       present(item["expires_at"]),
		Scope:           present(item["scope"]),
		RelationshipID:  present(item["relationship_id"]),
		GranteeMappedPK: present(item["grantee_mapped_pk"]),
		GranteePersonPK: present(item["grantee_person_pk"]),
	}
	if state, ok := item["state"]; ok {
		grant.StatePresent = true
		grant.State = value.Str(state)
	}
	if tied, ok := item["tied_competition_ids"].([]any); ok {
		for _, id := range tied {
			grant.Tied = append(grant.Tied, value.Str(id))
		}
	}
	if raw, ok := item["permissions"]; ok && raw != nil {
		grant.PermissionsSet = true
		if list, ok := raw.([]any); ok {
			grant.PermissionsList = true
			for _, entry := range list {
				if s, ok := entry.(string); ok {
					grant.Permissions = append(grant.Permissions, s)
				} else {
					grant.Permissions = append(grant.Permissions, "\x00invalid")
				}
			}
		}
	}
	return grant
}

func orEmpty(v any) any {
	if v == nil {
		return ""
	}
	return v
}

func (g Grant) isSlot() bool {
	return g.Entity == "relationship_slot" || strings.HasPrefix(g.SK, "RelationshipSlot#")
}

func GrantPermissions(grant Grant, dates map[string]string, now time.Time) []string {
	if grant.Revoked || (grant.StatePresent && grant.State != "approved") {
		return nil
	}
	switch grant.Role {
	case "coach", "handler":
		if len(grant.Tied) == 0 {
			return nil
		}
		var latest time.Time
		for _, id := range grant.Tied {
			raw, ok := dates[id]
			if !ok {
				return nil
			}
			day, valid := clock.Date(raw)
			if !valid {
				return nil
			}
			if day.After(latest) {
				latest = day
			}
		}
		if now.After(latest.AddDate(0, 0, 7).Add(24*time.Hour - time.Microsecond)) {
			return nil
		}
	case "peer", "read":
		if grant.ExpiresAt != "" {
			expires, aware, ok := clock.ParseISO(grant.ExpiresAt)
			if !ok || !aware || !now.Before(expires) {
				return nil
			}
		}
	default:
		return nil
	}
	permissions := grant.Permissions
	if !grant.PermissionsSet {
		switch grant.Role {
		case "coach":
			permissions = CoachPermissions
		case "handler":
			permissions = HandlerPermissions
		default:
			permissions = []string{"profile:read"}
		}
		if grant.Scope == "read" {
			permissions = filter(permissions, func(p string) bool { return strings.HasSuffix(p, ":read") })
		}
	} else if !grant.PermissionsList {
		return nil
	}
	readOnly := grant.Role == "peer" || grant.Role == "read"
	return filter(permissions, func(p string) bool {
		return slices.Contains(CoachPermissions, p) && (!readOnly || strings.HasSuffix(p, ":read"))
	})
}

func filter(values []string, keep func(string) bool) []string {
	var out []string
	for _, v := range values {
		if keep(v) {
			out = append(out, v)
		}
	}
	return out
}

func ActiveGrants(grants []Grant, dates map[string]string, now time.Time) []Grant {
	var out []Grant
	for _, index := range ActiveIndexes(grants, dates, now) {
		out = append(out, grants[index])
	}
	return out
}

func ActiveIndexes(grants []Grant, dates map[string]string, now time.Time) []int {
	slots := map[string]Grant{}
	for _, grant := range grants {
		if grant.isSlot() {
			slots[grant.Role] = grant
		}
	}
	var candidates []Grant
	var origin []int
	for index, grant := range grants {
		if len(GrantPermissions(grant, dates, now)) > 0 {
			candidates = append(candidates, grant)
			origin = append(origin, index)
		}
	}
	var result []int
	for position, grant := range candidates {
		if grant.Role == "coach" || grant.Role == "handler" {
			if slot, ok := slots[grant.Role]; ok {
				if slot.State != "active" || slot.RelationshipID != grant.RelationshipID {
					continue
				}
			} else {
				same := 0
				for _, other := range candidates {
					if other.Role == grant.Role {
						same++
					}
				}
				if same > 1 {
					continue
				}
			}
		}
		result = append(result, origin[position])
	}
	return result
}
