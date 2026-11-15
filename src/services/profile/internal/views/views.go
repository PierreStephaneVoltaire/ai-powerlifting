package views

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"slices"
	"sort"
	"strings"

	"golang.org/x/text/cases"

	"crypto/sha256"
	"encoding/hex"
	"powerlifting/profile/internal/access"
	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/tags"
	"powerlifting/profile/internal/value"
)

const pageSize = 20

var fold = cases.Fold()

type Views struct {
	DB     *store.DB
	People *people.Repo
	Access *access.Provider
	Tags   *tags.Catalog
	Env    clock.Env
}

func notFound() error { return apperr.New(404, "not_found", "Profile not found") }

func handleOf(owner value.Item) string {
	return value.Str(value.Or(owner["nickname"], value.Or(owner["username"], owner["pk"])))
}

func displayOf(owner value.Item) string {
	return value.Str(value.Or(owner["display_name"], handleOf(owner)))
}

func athleteOf(owner value.Item) string { return value.Str(value.Or(owner["mapped_pk"], owner["pk"])) }

func (v *Views) base(ctx context.Context, owner value.Item, granted *access.Context, vocabulary tags.Vocabulary) (map[string]any, error) {
	federations := []any{}
	for _, entry := range asList(owner["federations"]) {
		if s, ok := entry.(string); ok {
			federations = append(federations, s)
		}
	}
	selected, err := v.Tags.Selected(ctx, owner["tags"], vocabulary)
	if err != nil {
		return nil, err
	}
	visibility := "private"
	if owner["profile_visibility"] == "public" {
		visibility = "public"
	}
	roles := owner["roles"]
	if _, present := owner["roles"]; !present {
		roles = []any{"athlete"}
	}
	var federation any
	if len(federations) > 0 {
		federation = federations[0]
	}
	bio := owner["bio"]
	if _, present := owner["bio"]; !present {
		bio = ""
	}
	return map[string]any{
		"athlete_pk": athleteOf(owner), "nickname": value.Or(owner["nickname"], value.Or(owner["username"], owner["pk"])),
		"display_name": value.Or(owner["display_name"], value.Or(owner["nickname"], owner["pk"])), "avatar_url": owner["avatar_url"],
		"bio": bio, "profile_visibility": visibility, "public_training_summary_enabled": granted.Has("analytics:read"),
		"is_self": granted.IsSelf, "roles": roles, "federations": federations, "tags": selected.Approved(),
		"federation": federation, "weight_class_kg": nil, "practicing_for": nil,
		"summary":     Summary{}.Map(),
		"lift_videos": []any{},
	}, nil
}

func (v *Views) Visible(ctx context.Context, owner value.Item, actor string, vocabulary tags.Vocabulary, details bool) (map[string]any, error) {
	granted, err := v.Access.Context(ctx, actor, athleteOf(owner))
	if err != nil {
		return nil, err
	}
	if !granted.Has("profile:read") {
		return nil, nil
	}
	return v.detail(ctx, owner, granted, vocabulary, details)
}

func (v *Views) detail(ctx context.Context, owner value.Item, granted *access.Context, vocabulary tags.Vocabulary, details bool) (map[string]any, error) {
	result, err := v.base(ctx, owner, granted, vocabulary)
	if err != nil {
		return nil, err
	}
	athlete := athleteOf(owner)
	if details {
		result["sessions_public"] = granted.Has("program:read") && granted.Has("sessions:read")
	}
	programSK, program, err := v.CurrentProgram(ctx, athlete)
	if err != nil || program == nil {
		return result, err
	}
	meta := asMap(program["meta"])
	result["federation"] = value.Or(meta["federation"], result["federation"])
	if granted.Has("competition:read") {
		if n, ok := positive(meta["weight_class_kg"]); ok {
			result["weight_class_kg"] = n.JSON()
		}
		result["practicing_for"] = nilIfFalsy(meta["practicing_for"])
	}
	if details && (granted.Has("performance:read") || granted.Has("sessions:read") || granted.Has("lift-profiles:read")) {
		var sessions []map[string]any
		if granted.Has("sessions:read") || granted.Has("performance:read") {
			phases := asList(program["phases"])
			if sessions, err = v.Sessions(ctx, athlete, programSK, phases); err != nil {
				return nil, err
			}
		}
		derived := buildSummary(owner, program, sessions)
		if granted.Has("performance:read") {
			if sex, _ := owner["sex"].(string); sex == "male" || sex == "female" {
				result["sex"] = sex
			} else {
				result["sex"] = nil
			}
			summary := derived.Map()
			if !granted.Has("weight-log:read") {
				summary["bodyweight_kg"] = nil
			}
			result["summary"] = summary
		}
		if granted.Has("sessions:read") && granted.Has("videos:read") {
			videos := []any{}
			for _, entry := range derived.Videos {
				item := value.Copy(entry).(map[string]any)
				item["athlete_pk"] = athlete
				videos = append(videos, item)
			}
			result["lift_videos"] = videos
		}
		if granted.Has("lift-profiles:read") {
			profiles := liftProfiles(program, granted)
			result["lift_profiles"] = profiles
		}
	}
	return result, nil
}

func nilIfFalsy(v any) any {
	if value.Truthy(v) {
		return v
	}
	return nil
}

func liftProfiles(program map[string]any, granted *access.Context) any {
	raw, present := program["lift_profiles"]
	if !present {
		return []any{}
	}
	profiles := value.Copy(raw)
	if !granted.Has("videos:read") {
		for _, entry := range asList(profiles) {
			if profile, ok := entry.(map[string]any); ok {
				delete(profile, "form_videos")
			}
		}
	}
	return profiles
}

func (v *Views) GetByHandle(ctx context.Context, nickname, actor string) (map[string]any, error) {
	rows, err := v.People.All(ctx)
	if err != nil {
		return nil, err
	}
	var matches []value.Item
	for _, row := range rows {
		if strings.ToLower(handleOf(row)) == strings.ToLower(nickname) {
			matches = append(matches, row)
		}
	}
	if len(matches) != 1 {
		return nil, notFound()
	}
	return v.visibleOrNotFound(ctx, matches[0], actor)
}

func (v *Views) visibleOrNotFound(ctx context.Context, owner value.Item, actor string) (map[string]any, error) {
	vocabulary, err := v.Tags.Load(ctx)
	if err != nil {
		return nil, err
	}
	profile, err := v.Visible(ctx, owner, actor, vocabulary, true)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, notFound()
	}
	return profile, nil
}

func (v *Views) GetCurrent(ctx context.Context, pk, actor string) (map[string]any, error) {
	owner, err := v.People.Record(ctx, pk)
	if err != nil {
		return nil, err
	}
	if owner == nil {
		return nil, notFound()
	}
	return v.visibleOrNotFound(ctx, owner, actor)
}

type SearchArgs struct {
	Query       string
	Federations []string
	Tags        []string
	Mode        string
	Role        string
	Cursor      string
}

type found struct {
	display string
	handle  string
	owner   value.Item
	access  *access.Context
}

func fingerprint(query string, federations, requested []string, mode, role string) string {
	sortedFeds, sortedTags := slices.Clone(federations), slices.Clone(requested)
	sort.Strings(sortedFeds)
	sort.Strings(sortedTags)
	var roleValue any
	if role != "" {
		roleValue = role
	}
	payload := value.DumpSpaced([]any{query, anyList(sortedFeds), anyList(sortedTags), mode, roleValue})
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])
}

func anyList(values []string) []any {
	out := make([]any, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}

func (v *Views) Search(ctx context.Context, args SearchArgs, actor string) (map[string]any, error) {
	query := fold.String(people.Strip(args.Query))
	federationFilter := map[string]bool{}
	for _, federation := range args.Federations {
		federationFilter[federation] = true
	}
	requested := map[string]bool{}
	for _, tag := range args.Tags {
		name, ok := people.NormalizeTag(tag)
		if !ok {
			return nil, apperr.Validation("Tags must be 1–50 characters")
		}
		requested[name] = true
	}
	mode := args.Mode
	if mode == "" {
		mode = "and"
	}
	vocabulary, err := v.Tags.Load(ctx)
	if err != nil {
		return nil, err
	}
	requestedList := make([]string, 0, len(requested))
	for tag := range requested {
		if vocabulary.Status(tag) != "approved" {
			return map[string]any{"profiles": []any{}, "next_cursor": nil}, nil
		}
		requestedList = append(requestedList, tag)
	}
	fed := make([]string, 0, len(federationFilter))
	for federation := range federationFilter {
		fed = append(fed, federation)
	}
	print := fingerprint(query, fed, requestedList, mode, args.Role)
	var after []string
	if args.Cursor != "" {
		decoded, err := base64.URLEncoding.DecodeString(args.Cursor + strings.Repeat("=", (4-len(args.Cursor)%4)%4))
		var cursor struct {
			Filter string `json:"filter"`
			After  []any  `json:"after"`
		}
		if err != nil || json.Unmarshal(decoded, &cursor) != nil || cursor.Filter != print || len(cursor.After) != 2 {
			return nil, apperr.Validation("Invalid search cursor")
		}
		for _, entry := range cursor.After {
			text, ok := entry.(string)
			if !ok {
				return nil, apperr.Validation("Invalid search cursor")
			}
			after = append(after, text)
		}
	}
	owners, err := v.People.All(ctx)
	if err != nil {
		return nil, err
	}
	var matched []found
	for _, owner := range owners {
		roles := stringsOf(owner["roles"], []string{"athlete"}, owner)
		if args.Role != "" && !slices.Contains(roles, args.Role) {
			continue
		}
		if owner["profile_visibility"] == "public" && !slices.Contains(roles, "athlete") && !slices.Contains(roles, "coach") {
			continue
		}
		handle, display := handleOf(owner), displayOf(owner)
		key := found{display: fold.String(display), handle: handle}
		if after != nil && !(key.display > after[0] || (key.display == after[0] && key.handle > after[1])) {
			continue
		}
		if query != "" && !strings.Contains(fold.String(display), query) && !strings.Contains(fold.String(handle), query) {
			continue
		}
		if len(federationFilter) > 0 && !anyIn(federationFilter, stringsOf(owner["federations"], nil, owner)) {
			continue
		}
		selected, err := v.Tags.Selected(ctx, owner["tags"], vocabulary)
		if err != nil {
			return nil, err
		}
		approved := map[string]bool{}
		for _, tag := range selected {
			if tag.Approved {
				approved[tag.Name] = true
			}
		}
		if len(requested) > 0 {
			ok := false
			if mode == "and" {
				ok = true
				for tag := range requested {
					ok = ok && approved[tag]
				}
			} else {
				ok = anyIn(requested, keys(approved))
			}
			if !ok {
				continue
			}
		}
		granted, err := v.Access.Context(ctx, actor, athleteOf(owner))
		if err != nil {
			return nil, err
		}
		if !granted.Has("profile:read") {
			continue
		}
		key.owner, key.access = owner, granted
		matched = append(matched, key)
	}
	sort.SliceStable(matched, func(i, j int) bool {
		if matched[i].display != matched[j].display {
			return matched[i].display < matched[j].display
		}
		return matched[i].handle < matched[j].handle
	})
	page := matched
	if len(page) > pageSize {
		page = page[:pageSize]
	}
	profiles := make([]any, 0, len(page))
	for _, entry := range page {
		profile, err := v.detail(ctx, entry.owner, entry.access, vocabulary, false)
		if err != nil {
			return nil, err
		}
		profiles = append(profiles, profile)
	}
	var next any
	if len(matched) > pageSize {
		last := page[len(page)-1]
		cursor := `{"filter": ` + value.DumpSpaced(print) + `, "after": ` + value.DumpSpaced([]any{last.display, last.handle}) + `}`
		next = strings.TrimRight(base64.URLEncoding.EncodeToString([]byte(cursor)), "=")
	}
	return map[string]any{"profiles": profiles, "next_cursor": next}, nil
}

func keys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for key := range set {
		out = append(out, key)
	}
	return out
}

func anyIn(set map[string]bool, values []string) bool {
	for _, candidate := range values {
		if set[candidate] {
			return true
		}
	}
	return false
}

func stringsOf(raw any, fallback []string, owner value.Item) []string {
	list, ok := raw.([]any)
	if !ok {
		return fallback
	}
	out := make([]string, 0, len(list))
	for _, entry := range list {
		out = append(out, value.Str(entry))
	}
	return out
}
