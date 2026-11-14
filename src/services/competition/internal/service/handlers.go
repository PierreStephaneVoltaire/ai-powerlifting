package service

import (
	"context"
	"strconv"
	"strings"
	"time"

	"powerlifting/competition/internal/apperr"
	"powerlifting/competition/internal/attempts"
	"powerlifting/competition/internal/entries"
	"powerlifting/competition/internal/projection"
	"powerlifting/competition/internal/pyval"
	"powerlifting/competition/internal/store"
)

func (s *Service) calculateAttempts(ctx context.Context, arguments map[string]any) (any, error) {
	program, err := s.currentProgram(ctx, pk(arguments))
	if err != nil {
		return nil, err
	}
	lift, _ := arguments["lift"].(string)
	felt, _ := arguments["last_felt"].(string)
	request := attempts.Request{Lift: lift, Opener: arguments["opener_kg"], J1Override: arguments["j1_override"], J2Override: arguments["j2_override"], LastFelt: felt}
	return attempts.Calculate(request, attempts.PreferencesFrom(program)), nil
}

func (s *Service) currentProgram(ctx context.Context, athlete string) (map[string]any, error) {
	missing := apperr.NotFound("No program found for this athlete")
	pointer, err := s.Programs.Pointer(ctx, athlete)
	if err != nil {
		return nil, err
	}
	var sk string
	if pointer == nil {
		sk, err = s.latestVersion(ctx, athlete)
		if err != nil {
			return nil, err
		}
		if sk == "" {
			return nil, missing
		}
	} else if ref, present := pointer["ref_sk"]; present {
		sk = pyval.Str(ref)
	} else {
		sk = store.ProgramSKPrefix + pad(pointer["version"])
	}
	item, err := s.Programs.Item(ctx, athlete, sk)
	if err != nil {
		return nil, err
	}
	if item == nil {
		return nil, apperr.Internal("Program item not found at " + sk)
	}
	if item["published"] == false {
		return nil, missing
	}
	return item, nil
}

func pad(version any) string {
	number, _ := pyval.Float(version)
	text := strconv.Itoa(int(number))
	return strings.Repeat("0", max(3-len(text), 0)) + text
}

func (s *Service) latestVersion(ctx context.Context, athlete string) (string, error) {
	items, err := s.Programs.Versions(ctx, athlete)
	if err != nil {
		return "", err
	}
	best, latest := 0, ""
	for _, item := range items {
		if item["published"] == false {
			continue
		}
		sk, _ := item["sk"].(string)
		number, _, _ := strings.Cut(strings.TrimPrefix(sk, store.ProgramSKPrefix), "-")
		version, err := strconv.Atoi(number)
		if err == nil && version > best {
			best, latest = version, sk
		}
	}
	return latest, nil
}

func (s *Service) competitions(ctx context.Context, arguments map[string]any) (any, error) {
	athlete := pk(arguments)
	operation := textArg(arguments["op"])
	if operation == "" {
		switch {
		case pyval.Truthy(arguments["master_id"]) && arguments["patch"] != nil:
			operation = "update"
		case pyval.Truthy(arguments["master_id"]) && arguments["results"] != nil:
			operation = "complete"
		default:
			operation = "list"
		}
	}
	switch operation {
	case "list":
		list, err := s.rows.List(ctx, athlete, arguments)
		if err != nil {
			return nil, err
		}
		return map[string]any{"competitions": list}, nil
	case "update":
		return s.rows.Update(ctx, athlete, arguments)
	case "complete":
		return s.rows.Complete(ctx, athlete, arguments)
	}
	return nil, apperr.Validation("unknown op: " + operation)
}

func textArg(value any) string {
	if pyval.Truthy(value) {
		return pyval.Str(value)
	}
	return ""
}

func (s *Service) snapshot(ctx context.Context, arguments map[string]any) (any, error) {
	athlete := pk(arguments)
	dateText, _ := arguments["date"].(string)
	snapshotDate, ok := projection.ParseDay(dateText)
	if !ok {
		return nil, apperr.Validation("time data '" + dateText + "' does not match format '%Y-%m-%d'")
	}
	rows, err := s.Entries.QueryByDate(ctx, athlete)
	if err != nil {
		return nil, err
	}
	program, err := s.snapshotProgram(ctx, athlete, textArg(arguments["version"]), rows)
	if err != nil {
		return nil, err
	}
	target := snapshotDate.AddDate(0, 0, 7).Format("2006-01-02")
	retrospective := pyval.Truthy(arguments["allow_retrospective"])
	today := s.Today().UTC()
	today = time.Date(today.Year(), today.Month(), today.Day(), 0, 0, 0, 0, time.UTC)

	type update struct {
		sk     string
		name   any
		values []store.Field
		total  any
	}
	var updates []update
	var computed *projection.Projection
	evaluated := false
	for _, entry := range rows {
		status := pyval.Or(entry["user_status"], entry["status"])
		if pyval.Or(entry["start_date"], entry["date"]) != any(target) || entry["projected_at_t_minus_1w"] != nil {
			continue
		}
		if status != "confirmed" && status != "optional" && !(retrospective && status == "completed") {
			continue
		}
		if !evaluated {
			computed, _ = projection.Meet(program, target, snapshotDate, today)
			evaluated = true
		}
		if computed == nil {
			continue
		}
		fields := []store.Field{}
		for _, lift := range []string{"squat", "bench", "deadlift"} {
			var value any
			if projected, present := computed.Lifts[lift]; present {
				value = projected.Projected
			}
			fields = append(fields, store.Field{Name: lift + "_kg", Value: value})
		}
		fields = append(fields, store.Field{Name: "total_kg", Value: computed.Total})
		updates = append(updates, update{sk: entry["sk"].(string), name: entry["name"], values: fields})
	}

	now := entries.FormatTimestamp(s.Now())
	competitions := make([]any, 0, len(updates))
	for _, item := range updates {
		projectionValues := store.Projection{Values: item.values, SnapshotDate: dateText, UpdatedAt: now}
		projectionValues.SnapshotDate = snapshotDate.Format("2006-01-02")
		if err := s.Entries.SaveProjection(ctx, athlete, item.sk, projectionValues); err != nil {
			return nil, err
		}
		values := map[string]any{}
		for _, field := range item.values {
			values[field.Name] = field.Value
		}
		competitions = append(competitions, map[string]any{
			"date":                     target,
			"name":                     item.name,
			"projected_at_t_minus_1w":  values,
			"projection_snapshot_date": snapshotDate.Format("2006-01-02"),
		})
	}
	return map[string]any{"snapshot_date": snapshotDate.Format("2006-01-02"), "updated": len(updates), "competitions": competitions}, nil
}

func (s *Service) snapshotProgram(ctx context.Context, athlete, version string, rows []store.Item) (projection.Program, error) {
	if version == "" {
		version = "current"
	}
	var sk string
	if version == "current" {
		pointer, err := s.Programs.Pointer(ctx, athlete)
		if err != nil {
			return projection.Program{}, err
		}
		if ref := pointer["ref_sk"]; pyval.Truthy(ref) {
			sk = pyval.Str(ref)
		}
	} else {
		sk = "program#" + version
	}
	var item store.Item
	if sk != "" {
		var err error
		if item, err = s.Programs.Item(ctx, athlete, sk); err != nil {
			return projection.Program{}, err
		}
	}
	if item == nil {
		return projection.Program{}, apperr.Validation("Program version " + version + " not found")
	}
	items, err := s.Programs.Sessions(ctx, athlete, sk)
	if err != nil {
		return projection.Program{}, err
	}
	sessionItems := make([]map[string]any, len(items))
	for index, row := range items {
		sessionItems[index] = row
	}
	entryItems := make([]map[string]any, len(rows))
	for index, row := range rows {
		entryItems[index] = row
	}
	meta, _ := item["meta"].(map[string]any)
	return projection.Program{
		Meta:         meta,
		Sessions:     projection.SessionsFromItems(sessionItems),
		Competitions: projection.CompetitionsFromEntries(entryItems),
	}, nil
}
