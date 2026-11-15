package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"math"
	"strconv"
	"time"

	"powerlifting/profile/internal/apperr"
	"powerlifting/profile/internal/people"
	"powerlifting/profile/internal/store"
	"powerlifting/profile/internal/value"
)

type basics struct {
	MaxesDate  string
	Estimated  map[string]any
	Sex        string
	Country    any
	Region     any
	Bodyweight float64
	Maxes      [3]float64
}

func roundTwo(v float64) float64 {
	parsed, err := strconv.ParseFloat(strconv.FormatFloat(v, 'f', 2, 64), 64)
	if err != nil {
		return v
	}
	return parsed
}

func boundedKG(raw any, low, high float64, name string) (float64, error) {
	if raw == nil {
		return 0, apperr.Validation(name + " is required")
	}
	number, ok := people.Number(raw)
	if !ok {
		return 0, apperr.Validation(name + " must be a number")
	}
	if math.IsNaN(number) || math.IsInf(number, 0) {
		return 0, apperr.Validation(name + " must be a finite number")
	}
	if number < low || number > high {
		return 0, apperr.Validation(name + " must be between " + value.Float(low) + " and " + value.Float(high) + " kg")
	}
	return roundTwo(number), nil
}

func (s *Service) validateBasics(input map[string]any) (basics, error) {
	var out basics
	sex, _ := input["sex"].(string)
	if sex != "male" && sex != "female" {
		return out, apperr.Validation("sex must be 'male' or 'female'")
	}
	out.Sex = sex
	if country := input["country"]; country != nil {
		text, ok := country.(string)
		if !ok {
			return out, apperr.Validation("country must be a string")
		}
		if trimmed := people.Strip(text); trimmed != "" {
			if len([]rune(trimmed)) > 64 {
				return out, apperr.Validation("country must be at most 64 characters")
			}
			out.Country = trimmed
		}
	}
	if region := input["region"]; region != nil {
		text, ok := region.(string)
		if !ok {
			return out, apperr.Validation("region must be a string")
		}
		if trimmed := people.Strip(text); trimmed != "" {
			out.Region = people.Truncate(trimmed, 64)
		}
	}
	var err error
	if out.Bodyweight, err = boundedKG(input["bodyweight_kg"], 30, 300, "bodyweight_kg"); err != nil {
		return out, err
	}
	maxes, ok := input["training_maxes"].(map[string]any)
	if !ok {
		return out, apperr.Validation("training_maxes is required")
	}
	for i, lift := range people.Lifts {
		if out.Maxes[i], err = boundedKG(maxes[lift+"_kg"], 20, 600, lift+"_kg"); err != nil {
			return out, err
		}
	}
	today := s.deps.Env.Now().UTC().Format("2006-01-02")
	out.MaxesDate = today
	if given := input["maxes_date"]; value.Truthy(given) {
		text, ok := given.(string)
		if !ok {
			return out, apperr.Validation("Maxes date must be YYYY-MM-DD")
		}
		out.MaxesDate = text
	}
	parsed, err := time.Parse("2006-01-02", out.MaxesDate)
	if err != nil {
		return out, apperr.Validation("Maxes date must be YYYY-MM-DD")
	}
	if parsed.Format("2006-01-02") > today {
		return out, apperr.Validation("Maxes date cannot be in the future")
	}
	estimated, given := input["training_maxes_estimated"]
	object, isObject := estimated.(map[string]any)
	if !given {
		object, isObject = map[string]any{}, true
	}
	if !isObject {
		return out, apperr.Validation("Estimated maxes must identify squat, bench, or deadlift with booleans")
	}
	for key, flag := range object {
		if !containsString(people.Lifts, key) {
			return out, apperr.Validation("Estimated maxes must identify squat, bench, or deadlift with booleans")
		}
		if _, isBool := flag.(bool); !isBool {
			return out, apperr.Validation("Estimated maxes must identify squat, bench, or deadlift with booleans")
		}
	}
	out.Estimated = map[string]any{}
	for _, lift := range people.Lifts {
		out.Estimated[lift] = object[lift] == true
	}
	return out, nil
}

func (s *Service) updateAthleteBasics(ctx context.Context, req *Request) (any, error) {
	input := object(req.Args, "input")
	if len(input) == 0 {
		input = req.Args
	}
	validated, err := s.validateBasics(input)
	if err != nil {
		return nil, err
	}
	users, health := s.deps.DB.Tables.User, s.deps.DB.Tables.Health
	existing, err := s.deps.DB.Get(ctx, users, store.PK(req.PK()))
	if err != nil {
		return nil, err
	}
	roles, _ := existing["roles"].([]any)
	if existing == nil || !containsString(stringList(roles), "athlete") {
		return nil, apperr.Validation("The Athlete role is required")
	}
	athlete := value.Str(value.Or(existing["mapped_pk"], existing["pk"]))
	historyKey := store.PKSK(athlete, "max_history#current")
	history, err := s.deps.DB.Get(ctx, health, historyKey)
	if err != nil {
		return nil, err
	}
	trained := map[string]any{"squat_kg": validated.Maxes[0], "bench_kg": validated.Maxes[1], "deadlift_kg": validated.Maxes[2]}
	entry := map[string]any{"date": validated.MaxesDate, "squat_kg": validated.Maxes[0], "bench_kg": validated.Maxes[1], "deadlift_kg": validated.Maxes[2], "estimated": validated.Estimated, "source": "athlete_basics"}
	digest := sha256.Sum256([]byte(value.DumpSpaced(entry)))
	entryID := hex.EncodeToString(digest[:])
	entry["id"] = entryID
	entry["total_kg"] = validated.Maxes[0] + validated.Maxes[1] + validated.Maxes[2]
	now := s.deps.Env.Stamp()
	changes := []struct {
		key string
		val any
	}{
		{"maxes_date", validated.MaxesDate}, {"training_maxes_estimated", validated.Estimated}, {"sex", validated.Sex},
		{"country", validated.Country}, {"region", validated.Region}, {"bodyweight_kg", validated.Bodyweight},
		{"training_maxes", trained}, {"ranking_country", validated.Country}, {"ranking_region", validated.Region},
		{"athlete_basics_complete", true}, {"updated_at", now},
	}
	names := map[string]string{"#updated": "updated_at"}
	values := map[string]any{}
	expression := "SET "
	merged := value.CopyItem(existing)
	for i, change := range changes {
		alias, placeholder := "#f"+strconv.Itoa(i), ":v"+strconv.Itoa(i)
		names[alias] = change.key
		values[placeholder] = change.val
		if i > 0 {
			expression += ", "
		}
		expression += alias + " = " + placeholder
		merged[change.key] = change.val
	}
	condition := "attribute_not_exists(#updated)"
	if previous, ok := existing["updated_at"]; ok {
		condition = "#updated = :previous"
		values[":previous"] = previous
	}
	writes := []store.Write{{Kind: store.WriteUpdate, Table: users, Key: store.PK(value.Str(existing["pk"])), Update: expression, Condition: condition, Names: names, Values: values}}
	known, _ := history["basics_entry_ids"].([]any)
	if !containsString(stringList(known), entryID) {
		writes = append(writes, store.Write{
			Kind: store.WriteUpdate, Table: health, Key: historyKey,
			Update:    "SET entries = list_append(if_not_exists(entries, :empty), :entry), #version = :version, updated_at = :now ADD basics_entry_ids :ids",
			Condition: "attribute_not_exists(basics_entry_ids) OR NOT contains(basics_entry_ids, :id)",
			Names:     map[string]string{"#version": "version"},
			Values:    map[string]any{":empty": []any{}, ":entry": []any{entry}, ":version": "current", ":now": now, ":ids": value.StringSet{entryID}, ":id": entryID},
		})
	}
	if err := s.deps.DB.Transact(ctx, writes); err != nil {
		if errors.Is(err, store.ErrTransactionCanceled) {
			return nil, apperr.Conflict("conflict", "Your profile changed. Reload it before saving these basics.")
		}
		return nil, err
	}
	return s.people.Settings(merged).Map(), nil
}
