package markdown

import (
	"bytes"
	"text/template"
)

const sources = `
{{define "document"}}{{range $index, $section := .}}{{if $index}}

---

{{end}}{{$section}}{{end}}
{{end}}

{{define "overview"}}# {{.Name}}

{{join .Details " | "}}
{{if .Targets}}
### Target Lifts

{{join .Targets " / "}}
{{end}}{{if .Notes}}
{{range .Notes}}- {{.}}
{{end}}{{end}}{{end}}

{{define "goals"}}## Goals

{{if .HasPrimary}}**Primary goals:** {{.Primary}}

{{end}}{{if .HasSecondary}}**Secondary goals:** {{.Secondary}}

{{end}}{{.Table}}{{end}}

{{define "maxes"}}## Current Maxes

{{.Table}}{{end}}

{{define "history"}}## Max History

{{.Table}}{{end}}

{{define "phases"}}## Training Phases

{{range .Phases}}{{.Text}}
{{if .Notes}}{{.Notes}}
{{end}}
{{end}}{{end}}

{{define "sessions"}}## Training Log

{{range .Weeks}}### {{.Header}}

{{range .Sessions}}{{.Header}}
{{if .Wellness}}{{.Wellness}}
{{end}}{{if .Notes}}{{.Notes}}
{{end}}{{if .Table}}
{{.Table}}
{{end}}
{{end}}{{end}}{{end}}

{{define "competitions"}}## Competitions

{{range .Items}}### {{.Heading}}

{{if .Details}}{{.Details}}

{{end}}{{if .Targets}}{{.Targets}}
{{end}}{{if .Results}}{{.Results}}
{{end}}{{if .Table}}
{{.Table}}
{{end}}{{if .Context}}**Meet Context:** {{.Context}}
{{end}}{{range .Extras}}{{.}}
{{end}}{{if .Notes}}
{{.Notes}}
{{end}}
{{end}}{{end}}

{{define "biometrics"}}## Biometrics & Nutrition

{{.Summary}}

{{if .Averages}}{{.Averages}}

{{end}}{{.Table}}{{end}}

{{define "weightlog"}}## Weight Log

{{if .Empty}}No weight data recorded.{{else}}{{.Summary}}

{{.Table}}{{end}}{{end}}

{{define "supplements"}}## Supplements

{{if .Stack}}**Current stack:** {{.Stack}}

{{end}}{{range .Lines}}{{.}}
{{end}}{{end}}

{{define "liftprofiles"}}## Lift Profiles

{{range .Profiles}}**{{.Lift}}:** {{.Body}}.

{{end}}{{end}}

{{define "weekly"}}### Weekly Summary

{{range .Lines}}{{.}}
{{end}}{{if .Alerts}}
**Alerts:**
{{range .Alerts}}- {{.}}
{{end}}{{end}}{{if .Lifts}}
#### Per-Lift Progress

{{range .Lifts}}- **{{.}}**
{{end}}{{end}}{{if .Projections}}
#### Projections

{{range .Projections}}- {{.}}
{{end}}{{else if .Reason}}
No projections: {{.Reason}}
{{end}}{{end}}

{{define "dots"}}### e1RM Progression & DOTS Trend

{{if .Change}}{{.Change}}

{{end}}{{.Table}}

_Estimated 1RM via Epley formula. DOTS uses nearest bodyweight._
{{end}}

{{define "weighttrend"}}### Body Weight Trend

{{.Summary}}
{{if .Table}}
{{.Table}}
{{end}}{{end}}

{{define "analysis"}}## Analysis

{{if .Weekly}}{{template "weekly" .Weekly}}
{{end}}{{if .Dots}}{{template "dots" .Dots}}
{{end}}{{if .Weight}}{{template "weighttrend" .Weight}}
{{end}}{{end}}

{{define "notes"}}## Notes

{{range .Notes}}- **{{.Source}}** ({{.Context}}): {{.Note}}
{{end}}{{end}}
`

var layout = template.Must(template.New("markdown").Funcs(template.FuncMap{
	"join": func(values []string, separator string) string {
		out := ""
		for index, value := range values {
			if index > 0 {
				out += separator
			}
			out += value
		}
		return out
	},
}).Parse(sources))

func execute(name string, data any) (string, error) {
	var buffer bytes.Buffer
	if err := layout.ExecuteTemplate(&buffer, name, data); err != nil {
		return "", err
	}
	return buffer.String(), nil
}
