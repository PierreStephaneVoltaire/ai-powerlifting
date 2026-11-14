package session

import (
	"cmp"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"

	"powerlifting/sessions/internal/value"
)

const skPrefix = "session#"

var internalFields = []string{
	"pk", "sk", "entity_type", "source_pk", "source_table", "program_sk", "program_version",
	"program_version_number", "source_index", "same_day_ordinal", "phase_ref", "session_id",
}

func prefix(programSK string) string { return skPrefix + programSK + "#" }

func public(item value.Item, phases []any) value.Item {
	session := value.Sanitize(item).(map[string]any)
	if sessionID, present := session["session_id"]; present {
		if _, hasID := session["id"]; !hasID {
			session["id"] = value.Str(sessionID)
		}
	}
	for _, key := range internalFields {
		delete(session, key)
	}
	phase := resolvePhase(session, phases)
	session["week_number"] = value.Int(parseWeek(session))
	session["block"] = value.Str(value.Or(session["block"], defaultBlock))
	session["block_id"] = value.Str(value.Or(session["block_id"], session["block"]))
	session["phase"] = phase
	session["phase_name"] = value.Str(value.Or(phase["name"], unscheduled))
	return session
}

func withPhase(item value.Item, phases []any) value.Item {
	result := public(item, nil)
	result["phase"] = resolvePhase(result, phases)
	return result
}

func sortItems(items []value.Item) {
	slices.SortStableFunc(items, func(a, b value.Item) int {
		return cmp.Or(
			strings.Compare(value.Str(value.Or(a["date"], "")), value.Str(value.Or(b["date"], ""))),
			cmp.Compare(value.IntOf(a["same_day_ordinal"], 0), value.IntOf(b["same_day_ordinal"], 0)),
			cmp.Compare(value.IntOf(a["source_index"], 0), value.IntOf(b["source_index"], 0)),
			strings.Compare(value.Str(value.Or(a["sk"], "")), value.Str(value.Or(b["sk"], ""))),
		)
	})
}

func identity(item value.Item) string {
	return strings.TrimSpace(value.Str(value.Or(item["session_id"], value.Or(item["id"], ""))))
}

func rawIdentity(item value.Item) string {
	return value.Str(value.Or(item["session_id"], value.Or(item["id"], "")))
}

func isoTime(now time.Time) string {
	now = now.UTC()
	text := now.Format("2006-01-02T15:04:05")
	if micro := now.Nanosecond() / 1000; micro != 0 {
		text += fmt.Sprintf(".%06d", micro)
	}
	return text + "+00:00"
}

func versionNumber(programSK string) any {
	rest, ok := strings.CutPrefix(programSK, "program#v")
	if !ok {
		return nil
	}
	n, err := strconv.Atoi(strings.TrimSpace(rest))
	if err != nil {
		return nil
	}
	return value.Int(n)
}

type draft struct {
	programSK string
	session   value.Item
	phases    []any
	existing  value.Item
	sourceIdx int
	sameDay   int
	siblings  []value.Item
}

func (s *Service) build(pk string, d draft) value.Item {
	session := value.CopyItem(d.session)
	date := value.Str(value.Or(session["date"], "undated"))
	sessionID := s.chooseID(d.existing["session_id"], session["id"], session["session_id"])
	sameDayCount := func() int {
		datePrefix := prefix(d.programSK) + date + "#"
		count := 0
		for _, sibling := range d.siblings {
			if strings.HasPrefix(value.Str(sibling["sk"]), datePrefix) {
				count++
			}
		}
		return count + 1
	}
	ordinal := d.sameDay
	if ordinal == 0 {
		ordinal = value.IntOf(d.existing["same_day_ordinal"], 0)
	}
	if ordinal <= 0 {
		ordinal = sameDayCount()
	}

	block := value.Str(value.Or(session["block"], defaultBlock))
	blockID := value.Str(value.Or(session["block_id"], block))
	fallbackStatus := "planned"
	if value.Truthy(session["completed"]) {
		fallbackStatus = "completed"
	}
	status := value.Str(value.Or(session["status"], fallbackStatus))
	completed := value.Truthy(session["completed"]) || status == "logged" || status == "completed"
	phaseInput := value.CopyItem(session)
	phaseInput["block"] = block
	phase := resolvePhase(phaseInput, d.phases)
	planned, ok := session["planned_exercises"].([]any)
	if !ok {
		planned = []any{}
	}
	week := parseWeek(session)

	session["id"] = sessionID
	session["session_id"] = sessionID
	session["date"] = date
	session["block"] = block
	session["block_id"] = blockID
	session["status"] = status
	session["completed"] = completed
	session["week_number"] = value.Int(week)
	session["phase"] = phase
	session["phase_name"] = value.Str(value.Or(phase["name"], unscheduled))
	session["planned_exercises"] = planned

	if d.existing != nil {
		if videos, present := d.existing["videos"]; present {
			session["videos"] = value.Copy(videos)
		} else {
			delete(session, "videos")
		}
		if revision, present := d.existing["media_revision"]; present {
			session["media_revision"] = revision
		} else {
			delete(session, "media_revision")
		}
	}
	if exercises, ok := session["exercises"].([]any); ok {
		for _, entry := range exercises {
			if exercise, ok := value.Map(entry); ok {
				s.assignSetIDs(exercise)
			}
		}
	}

	sk, _ := d.existing["sk"].(string)
	if sk == "" || !strings.Contains(sk, "#"+date+"#") {
		ordinal = d.sameDay
		if ordinal == 0 {
			ordinal = sameDayCount()
		}
		sk = fmt.Sprintf("%s%s#%03d#%s", prefix(d.programSK), date, ordinal, sessionID)
	}

	session["pk"] = pk
	session["sk"] = sk
	session["entity_type"] = "session"
	session["source_pk"] = pk
	session["source_table"] = s.SourceTable
	session["program_sk"] = d.programSK
	session["program_version"] = strings.TrimPrefix(d.programSK, "program#")
	session["program_version_number"] = versionNumber(d.programSK)
	session["source_index"] = value.Int(value.IntOf(d.existing["source_index"], d.sourceIdx))
	session["same_day_ordinal"] = value.Int(ordinal)
	session["phase_ref"] = phaseRef(phase)
	session["updated_at"] = isoTime(s.Now())
	return session
}

func (s *Service) assignSetIDs(exercise value.Item) {
	count := value.IntOf(exercise["sets"], 0)
	existing, _ := exercise["set_ids"].([]any)
	ids := make([]any, 0, max(count, 0))
	for i := 0; i < count; i++ {
		if i < len(existing) && value.Truthy(existing[i]) {
			ids = append(ids, value.Str(existing[i]))
		} else {
			ids = append(ids, s.NewID())
		}
	}
	exercise["set_ids"] = ids
}

func (s *Service) chooseID(candidates ...any) string {
	for _, candidate := range candidates {
		if value.Truthy(candidate) {
			return value.Str(candidate)
		}
	}
	return s.NewID()
}
