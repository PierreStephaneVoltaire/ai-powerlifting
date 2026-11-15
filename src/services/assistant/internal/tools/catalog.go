package tools

import (
	"slices"
	"sort"
)

const (
	SurfaceGeneral       = "general"
	SurfaceTemplatePhase = "template-phase"
	SurfaceSessionDesign = "session-design"
	SurfaceGoals         = "goals"
	SurfaceSupplements   = "supplements"
	SurfaceBiometrics    = "biometrics"
	SurfaceResearch      = "research"
)

type Operation struct {
	Permission  string
	Mutating    bool
	Destructive bool
}

var operations = map[string]Operation{
	"session_get":                     {Permission: "sessions:read"},
	"session_list":                    {Permission: "sessions:read"},
	"session_list_full":               {Permission: "sessions:read"},
	"health_get_sessions_range":       {Permission: "sessions:read"},
	"session_create":                  {Permission: "sessions:write", Mutating: true},
	"session_patch":                   {Permission: "sessions:write", Mutating: true},
	"session_patch_by_date":           {Permission: "sessions:write", Mutating: true},
	"session_replace":                 {Permission: "sessions:write", Mutating: true},
	"session_delete":                  {Permission: "sessions:write", Mutating: true, Destructive: true},
	"session_replace_all":             {Permission: "sessions:write", Mutating: true, Destructive: true},
	"program_get":                     {Permission: "program:read"},
	"program_list_full":               {Permission: "program:read"},
	"program_update_phases":           {Permission: "program:write", Mutating: true},
	"health_get_supplements":          {Permission: "program:read"},
	"health_get_diet_notes":           {Permission: "program:read"},
	"supplement_phases_update":        {Permission: "program:write", Mutating: true},
	"diet_notes_update":               {Permission: "program:write", Mutating: true},
	"template_get":                    {Permission: "templates:read"},
	"template_list":                   {Permission: "templates:read"},
	"template_report":                 {Permission: "templates:read"},
	"template_patch":                  {Permission: "templates:write", Mutating: true},
	"template_update":                 {Permission: "templates:write", Mutating: true},
	"template_evaluate":               {Permission: "templates:write", Mutating: true},
	"goals_list":                      {Permission: "goals:read"},
	"goals_replace":                   {Permission: "goals:write", Mutating: true, Destructive: true},
	"max_target_get":                  {Permission: "performance:read"},
	"max_target_update":               {Permission: "performance:write", Mutating: true},
	"max_history_get":                 {Permission: "performance:read"},
	"max_history_add":                 {Permission: "performance:write", Mutating: true},
	"health_get_current_maxes":        {Permission: "performance:read"},
	"health_update_current_maxes":     {Permission: "performance:write", Mutating: true},
	"weight_log_get":                  {Permission: "weight-log:read"},
	"weight_log_add":                  {Permission: "weight-log:write", Mutating: true},
	"weight_log_remove":               {Permission: "weight-log:write", Mutating: true, Destructive: true},
	"exercise_get_glossary":           {Permission: "glossary:read"},
	"estimate_1rm":                    {Permission: "calculations:read"},
	"pct_of_max":                      {Permission: "calculations:read"},
	"calculate_dots":                  {Permission: "calculations:read"},
	"calculate_attempts":              {Permission: "competition:read"},
	"health_list_competitions":        {Permission: "competition:read"},
	"analytics.lifetime":              {Permission: "analytics:read"},
	"analytics.weekly":                {Permission: "analytics:read"},
	"analytics.compare":               {Permission: "analytics:read"},
	"analyze_progression":             {Permission: "analytics:read"},
	"analyze_rpe_drift":               {Permission: "analytics:read"},
	"analyze_powerlifting_stats":      {Permission: "analytics:read"},
	"powerlifting_ranking_percentile": {Permission: "analytics:read"},
	"powerlifting_filter_categories":  {Permission: "analytics:read"},
}

type Surface struct {
	Name      string
	Reads     []string
	Writes    []string
	Delegates []string
}

var surfaces = map[string]Surface{
	SurfaceSessionDesign: {
		Name:      SurfaceSessionDesign,
		Reads:     []string{"session_get", "session_list", "session_list_full", "health_get_sessions_range", "program_get", "health_get_current_maxes", "exercise_get_glossary", "estimate_1rm", "pct_of_max"},
		Writes:    []string{"session_create", "session_patch", "session_patch_by_date", "session_replace", "session_delete", "session_replace_all"},
		Delegates: []string{SurfaceResearch},
	},
	SurfaceTemplatePhase: {
		Name:      SurfaceTemplatePhase,
		Reads:     []string{"template_get", "template_list", "template_report", "program_get", "exercise_get_glossary", "health_get_current_maxes"},
		Writes:    []string{"template_patch", "template_update", "template_evaluate", "program_update_phases"},
		Delegates: []string{SurfaceResearch, SurfaceSessionDesign},
	},
	SurfaceGoals: {
		Name:      SurfaceGoals,
		Reads:     []string{"goals_list", "max_target_get", "health_get_current_maxes", "health_list_competitions", "calculate_attempts"},
		Writes:    []string{"goals_replace", "max_target_update"},
		Delegates: []string{SurfaceResearch},
	},
	SurfaceSupplements: {
		Name:      SurfaceSupplements,
		Reads:     []string{"health_get_supplements", "health_get_diet_notes"},
		Writes:    []string{"supplement_phases_update", "diet_notes_update"},
		Delegates: []string{SurfaceResearch},
	},
	SurfaceBiometrics: {
		Name:      SurfaceBiometrics,
		Reads:     []string{"weight_log_get", "max_history_get", "health_get_current_maxes", "calculate_dots"},
		Writes:    []string{"weight_log_add", "weight_log_remove", "max_history_add", "health_update_current_maxes"},
		Delegates: []string{SurfaceResearch},
	},
	SurfaceResearch: {
		Name: SurfaceResearch,
		Reads: []string{
			"analytics.lifetime", "analytics.weekly", "analytics.compare", "analyze_progression", "analyze_rpe_drift", "analyze_powerlifting_stats",
			"powerlifting_ranking_percentile", "powerlifting_filter_categories", "exercise_get_glossary", "health_list_competitions", "session_list", "program_get",
			"max_history_get", "weight_log_get", "health_get_current_maxes",
		},
		Delegates: []string{SurfaceResearch},
	},
}

func SubagentKinds() []string {
	var kinds []string
	for name := range surfaces {
		kinds = append(kinds, name)
	}
	sort.Strings(kinds)
	return kinds
}

func LookupSurface(name string) (Surface, bool) {
	if name == SurfaceGeneral {
		return General(), true
	}
	surface, ok := surfaces[name]
	return surface, ok
}

func General() Surface {
	reads := map[string]bool{}
	var delegates []string
	for _, surface := range surfaces {
		for _, name := range surface.Reads {
			reads[name] = true
		}
		delegates = append(delegates, surface.Name)
	}
	general := Surface{Name: SurfaceGeneral, Delegates: delegates}
	for name := range reads {
		general.Reads = append(general.Reads, name)
	}
	sort.Strings(general.Reads)
	sort.Strings(general.Delegates)
	return general
}

func (s Surface) Allows(name string) bool {
	return slices.Contains(s.Reads, name) || slices.Contains(s.Writes, name)
}

func (s Surface) CanDelegate(kind string) bool {
	return kind == s.Name && kind != SurfaceGeneral || slices.Contains(s.Delegates, kind)
}

func Lookup(name string) (Operation, bool) {
	operation, ok := operations[name]
	return operation, ok
}

func IsMutating(name string) bool {
	operation, ok := operations[name]
	return !ok || operation.Mutating
}

func IsDestructive(name string) bool {
	return operations[name].Destructive
}

func Scope(surface Surface, permissions []string) []string {
	var scope []string
	for _, name := range append(slices.Clone(surface.Reads), surface.Writes...) {
		operation, ok := operations[name]
		if ok && slices.Contains(permissions, operation.Permission) {
			scope = append(scope, name)
		}
	}
	sort.Strings(scope)
	return slices.Compact(scope)
}

func Permission(name string) string {
	return operations[name].Permission
}
