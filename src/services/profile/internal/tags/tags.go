package tags

import (
	"context"
	"errors"
	"slices"
	"sort"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/clock"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

type Vocabulary map[string]value.Item

func (v Vocabulary) Status(tag string) string {
	if item, ok := v[tag]; ok {
		if status, ok := item["status"].(string); ok {
			return status
		}
	}
	return ""
}

type SelectedTag struct {
	Name     string
	Approved bool
	Status   string
}

type Selected []SelectedTag

func (s Selected) Maps() []any {
	out := make([]any, len(s))
	for i, tag := range s {
		out[i] = map[string]any{"tag": tag.Name, "approved": tag.Approved, "status": tag.Status, "proposed_by": ""}
	}
	return out
}

func (s Selected) Approved() []any {
	out := []any{}
	for _, tag := range s {
		if tag.Approved {
			out = append(out, tag.Name)
		}
	}
	return out
}

func (s Selected) Has(name string) bool {
	return slices.ContainsFunc(s, func(tag SelectedTag) bool { return people.TagKey(tag.Name) == people.TagKey(name) })
}

type Catalog struct {
	DB     *store.DB
	People *people.Repo
	Env    clock.Env
}

func (c *Catalog) Load(ctx context.Context) (Vocabulary, error) {
	rows, err := c.DB.Query(ctx, store.Query{
		Table:      c.DB.Tables.Tags,
		KeyCond:    "pk = :pk",
		Values:     map[string]any{":pk": "Catalog"},
		Consistent: true,
	})
	if err != nil {
		return nil, err
	}
	vocabulary := Vocabulary{}
	for _, row := range rows {
		vocabulary[value.Str(row["tag"])] = row
	}
	return vocabulary, nil
}

func names(raw any) []string {
	list, _ := raw.([]any)
	var out []string
	for _, item := range list {
		candidate := item
		if object, ok := item.(map[string]any); ok {
			candidate = object["tag"]
		}
		name, ok := people.NormalizeTag(candidate)
		if !ok {
			continue
		}
		if !slices.ContainsFunc(out, func(existing string) bool { return people.TagKey(existing) == people.TagKey(name) }) {
			out = append(out, name)
		}
	}
	return out
}

func (c *Catalog) Selected(ctx context.Context, raw any, vocabulary Vocabulary) (Selected, error) {
	selected := names(raw)
	if len(selected) > people.MaxTags {
		selected = selected[:people.MaxTags]
	}
	if len(selected) > 0 && vocabulary == nil {
		var err error
		if vocabulary, err = c.Load(ctx); err != nil {
			return nil, err
		}
	}
	out := make(Selected, len(selected))
	for i, name := range selected {
		status := vocabulary.Status(name)
		out[i] = SelectedTag{Name: name, Approved: status == "approved", Status: status}
		if status == "" {
			out[i].Status = "pending"
		}
	}
	return out, nil
}

func Canonical(name string, vocabulary Vocabulary) string {
	keys := make([]string, 0, len(vocabulary))
	for existing := range vocabulary {
		keys = append(keys, existing)
	}
	sort.Strings(keys)
	for _, existing := range keys {
		if people.TagKey(existing) == people.TagKey(name) {
			return existing
		}
	}
	return name
}

func (c *Catalog) Listing(ctx context.Context, settingsPK string, includePending, operator bool) (map[string]any, error) {
	if includePending && !operator {
		return nil, apperr.Forbidden("Only the operator may review the catalog")
	}
	personal := map[string]bool{}
	if settingsPK != "" {
		owner, err := c.People.Get(ctx, settingsPK)
		if err != nil {
			return nil, err
		}
		for _, tag := range names(owner["tags"]) {
			personal[tag] = true
		}
	}
	vocabulary, err := c.Load(ctx)
	if err != nil {
		return nil, err
	}
	rows := make([]string, 0, len(vocabulary))
	for tag := range vocabulary {
		rows = append(rows, tag)
	}
	sort.Strings(rows)
	listed := []any{}
	for _, tag := range rows {
		status := value.Str(vocabulary[tag]["status"])
		if includePending || status == "approved" || personal[tag] {
			listed = append(listed, map[string]any{"tag": tag, "status": status})
		}
	}
	return map[string]any{"tags": listed}, nil
}

func (c *Catalog) Decide(ctx context.Context, operator bool, person, tag, decision string) (map[string]any, error) {
	if !operator {
		return nil, apperr.Forbidden("Only the operator may approve vocabulary")
	}
	normalized, ok := people.NormalizeTag(tag)
	if !ok {
		return nil, apperr.Validation(invalidTag(tag))
	}
	vocabulary, err := c.Load(ctx)
	if err != nil {
		return nil, err
	}
	name := Canonical(normalized, vocabulary)
	if decision == "" {
		decision = "approved"
	}
	if decision != "approved" && decision != "rejected" {
		return nil, apperr.Validation("Decision must be approved or rejected")
	}
	key := store.PKSK("Catalog", "Tag#"+name)
	current, err := c.DB.Get(ctx, c.DB.Tables.Tags, key)
	if err != nil {
		return nil, err
	}
	item := value.Item{}
	for k, v := range current {
		item[k] = v
	}
	item["pk"], item["sk"], item["tag"], item["status"] = "Catalog", "Tag#"+name, name, decision
	item["decided_by"], item["updated_at"] = person, c.Env.Stamp()
	if err := c.DB.Put(ctx, c.DB.Tables.Tags, item, ""); err != nil {
		return nil, err
	}
	return map[string]any{"tag": name, "status": decision}, nil
}

func invalidTag(raw any) string {
	if _, ok := raw.(string); !ok {
		return "Tag must be text"
	}
	return "Tags must be 1–50 characters"
}

type Selection struct {
	Person         string
	Athlete        string
	Tag            string
	TargetNickname string
	Remove         bool
}

func (c *Catalog) Select(ctx context.Context, selection Selection, settingsPK string) (map[string]any, error) {
	name, ok := people.NormalizeTag(selection.Tag)
	if !ok {
		return nil, apperr.Validation(invalidTag(selection.Tag))
	}
	if settingsPK == "" || settingsPK != selection.Athlete {
		return nil, apperr.Forbidden("Authenticated profile owner required")
	}
	current, err := c.People.Get(ctx, settingsPK)
	if err != nil {
		return nil, err
	}
	if current == nil {
		return nil, apperr.Validation("Profile not found")
	}
	if selection.TargetNickname != "" && selection.TargetNickname != value.Str(current["nickname"]) {
		return nil, apperr.Forbidden("Tags can only be selected for your own profile")
	}
	vocabulary, err := c.Load(ctx)
	if err != nil {
		return nil, err
	}
	name = Canonical(name, vocabulary)
	selected, err := c.Selected(ctx, current["tags"], vocabulary)
	if err != nil {
		return nil, err
	}
	if !selection.Remove && !selected.Has(name) && len(selected) >= people.MaxTags {
		return nil, apperr.Validation("A profile can have at most twenty tags")
	}
	now := c.Env.Stamp()
	if _, known := vocabulary[name]; !selection.Remove && !known {
		pending := value.Item{"pk": "Catalog", "sk": "Tag#" + name, "tag": name, "status": "pending", "requested_by": settingsPK, "created_at": now}
		if err := c.DB.Put(ctx, c.DB.Tables.Tags, pending, "attribute_not_exists(pk)"); err != nil && !errors.Is(err, store.ErrConditionFailed) {
			return nil, err
		}
	}
	stored := []any{}
	for _, tag := range selected {
		if people.TagKey(tag.Name) != people.TagKey(name) {
			stored = append(stored, map[string]any{"tag": tag.Name, "approved": tag.Approved, "status": tag.Status, "proposed_by": ""})
		}
	}
	if !selection.Remove {
		stored = append(stored, map[string]any{"tag": name})
	}
	if err := c.People.Update(ctx, settingsPK, store.Update{
		Expression: "SET tags = :tags, updated_at = :now",
		Values:     map[string]any{":tags": stored, ":now": now},
	}); err != nil {
		return nil, err
	}
	fresh, err := c.Selected(ctx, stored, nil)
	if err != nil {
		return nil, err
	}
	merged := value.Item{}
	for k, v := range current {
		merged[k] = v
	}
	merged["tags"], merged["updated_at"] = fresh.Maps(), now
	return people.Normalize(merged, c.Env.Now(), clock.ISO).Map(), nil
}
