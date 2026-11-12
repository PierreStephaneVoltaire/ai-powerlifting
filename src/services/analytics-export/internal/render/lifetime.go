package render

import (
	"strings"
)

type Lifetime struct {
	Athlete     string
	GeneratedAt string
	BlockKeys   []string
	Report      map[string]any
	Narrative   map[string]any
}

func (l Lifetime) tables() []Table {
	tables := []Table{
		{"Overview", "Overview", l.overviewRows()},
		{"Blocks", "Blocks", l.blockRows()},
		{"Classification", "Classification", l.classificationRows()},
		{"Correlations", "Correlations", l.correlationRows()},
		{"What Worked", "Worked", signalRows(l.Report["worked"])},
		{"What Did Not Work", "Did Not Work", signalRows(l.Report["did_not_work"])},
		{"Data Limits", "Data Limits", limitRows(l.Report["data_limits"])},
		{"Narrative", "Narrative", l.narrativeRows()},
	}
	present := tables[:0]
	for _, table := range tables {
		if len(table.Rows) > 0 {
			present = append(present, table)
		}
	}
	return present
}

func (l Lifetime) Markdown() string {
	lines := []string{
		"# Lifetime Analysis " + l.Athlete,
		"",
		"Generated: " + l.GeneratedAt,
	}
	for _, table := range l.tables() {
		lines = append(lines, "", "## "+table.Title)
		lines = append(lines, markdownTable(table.Rows)...)
	}
	return strings.Join(lines, "\n") + "\n"
}

func (l Lifetime) Workbook() ([]byte, error) {
	return workbook(l.tables())
}

func (l Lifetime) overviewRows() []Row {
	return []Row{
		{"Metric", "Value"},
		{"Athlete", l.Athlete},
		{"Generated", l.GeneratedAt},
		{"Blocks analyzed", l.Report["block_count"]},
		{"Minimum block weeks", l.Report["min_block_weeks"]},
		{"Block keys", strings.Join(l.BlockKeys, "; ")},
	}
}

func (l Lifetime) blockRows() []Row {
	blocks := list(l.Report["blocks"])
	if len(blocks) == 0 {
		return nil
	}
	rows := []Row{{"Block", "Start", "End", "Weeks", "Verdict", "Squat e1RM", "Bench e1RM", "Deadlift e1RM", "DOTS", "Competition"}}
	for _, raw := range blocks {
		item := record(raw)
		outcome := record(item["outcome"])
		e1rm := record(outcome["e1rm"])
		competition := record(outcome["competition"])
		rows = append(rows, Row{
			text(item["label"]), text(item["start_date"]), text(item["end_date"]), item["week_count"],
			text(record(record(item["classification"])["overall"])["label"]),
			formatDelta(e1rm["squat"]), formatDelta(e1rm["bench"]), formatDelta(e1rm["deadlift"]),
			formatDelta(outcome["dots"]), text(competition["name"]),
		})
	}
	return rows
}

func formatDelta(change any) string {
	delta := record(change)["delta"]
	if value, ok := number(delta); ok {
		return fixed(value, 1)
	}
	return "--"
}

func (l Lifetime) classificationRows() []Row {
	classification := record(l.Report["classification"])
	overall, perLift := record(classification["overall"]), record(classification["per_lift"])
	if len(overall) == 0 {
		return nil
	}
	counts := func(label string, value map[string]any) Row {
		return Row{label, numberOrBlank(value["improved"]), numberOrBlank(value["stalled"]), numberOrBlank(value["regressed"]), numberOrBlank(value["insufficient_data"])}
	}
	rows := []Row{{"Lift", "Improved", "Stalled", "Regressed", "Insufficient data"}, counts("Overall", overall)}
	for _, lift := range liftOrder(perLift) {
		rows = append(rows, counts(titleize(lift), record(perLift[lift])))
	}
	return rows
}

func (l Lifetime) correlationRows() []Row {
	correlations := list(l.Report["correlations"])
	if len(correlations) == 0 {
		return nil
	}
	rows := []Row{{"Exposure", "Outcome", "Lift", "N", "Kendall tau", "p", "Direction", "Strength"}}
	for _, raw := range correlations {
		item := record(raw)
		kendall := record(item["kendall"])
		rows = append(rows, Row{
			text(item["exposure"]), text(item["outcome"]), text(item["lift"]), item["n"],
			formatNumber(kendall["tau"], 2), formatNumber(kendall["p"], 3), text(item["direction"]), text(item["strength"]),
		})
	}
	return rows
}

func signalRows(value any) []Row {
	signals := list(value)
	if len(signals) == 0 {
		return nil
	}
	rows := []Row{{"Variable", "Outcome", "Lift", "Statement", "Strength", "N"}}
	for _, raw := range signals {
		item := record(raw)
		rows = append(rows, Row{text(item["variable"]), text(item["outcome"]), text(item["lift"]), text(item["statement"]), text(item["strength"]), item["n"]})
	}
	return rows
}

func limitRows(value any) []Row {
	limits := list(value)
	if len(limits) == 0 {
		return nil
	}
	rows := []Row{{"Limit"}}
	for _, limit := range limits {
		rows = append(rows, Row{limit})
	}
	return rows
}

func (l Lifetime) narrativeRows() []Row {
	if len(l.Narrative) == 0 {
		return nil
	}
	rows := []Row{{"Section", "Text"}}
	for _, key := range sortedKeys(l.Narrative) {
		label := titleize(key)
		if items, ok := l.Narrative[key].([]any); ok {
			for _, item := range items {
				rows = append(rows, Row{label, compact(item)})
			}
		} else {
			rows = append(rows, Row{label, compact(l.Narrative[key])})
		}
	}
	return rows
}
