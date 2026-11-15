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

type Profile struct {
	Name            string
	Hint            string
	DefaultDelegate string
}

var profiles = map[string]Profile{
	SurfaceGeneral:       {Name: SurfaceGeneral, Hint: "Answer questions about the Athlete's training and act on any part of the portal the Person asks about.", DefaultDelegate: SurfaceResearch},
	SurfaceSessionDesign: {Name: SurfaceSessionDesign, Hint: "The Person is designing or adjusting a training session and its exercises.", DefaultDelegate: SurfaceSessionDesign},
	SurfaceTemplatePhase: {Name: SurfaceTemplatePhase, Hint: "The Person is shaping the phases of a training template and its weeks.", DefaultDelegate: SurfaceTemplatePhase},
	SurfaceGoals:         {Name: SurfaceGoals, Hint: "The Person is reviewing or updating the Athlete's goals and targets.", DefaultDelegate: SurfaceGoals},
	SurfaceSupplements:   {Name: SurfaceSupplements, Hint: "The Person is reviewing or updating supplement and diet plans.", DefaultDelegate: SurfaceSupplements},
	SurfaceBiometrics:    {Name: SurfaceBiometrics, Hint: "The Person is reviewing or recording body weight and max history.", DefaultDelegate: SurfaceBiometrics},
	SurfaceResearch:      {Name: SurfaceResearch, Hint: "The Person wants read-only research across the Athlete's data, reported with numbers.", DefaultDelegate: SurfaceResearch},
}

func SubagentKinds() []string {
	var kinds []string
	for name := range profiles {
		if name != SurfaceGeneral {
			kinds = append(kinds, name)
		}
	}
	sort.Strings(kinds)
	return kinds
}

func LookupProfile(name string) (Profile, bool) {
	if name == "" {
		name = SurfaceGeneral
	}
	profile, ok := profiles[name]
	return profile, ok
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

func Scope(permissions []string) []string {
	var scope []string
	for name, operation := range operations {
		if slices.Contains(permissions, operation.Permission) {
			scope = append(scope, name)
		}
	}
	sort.Strings(scope)
	return scope
}

func Writes(scope []string) []string {
	var writes []string
	for _, name := range scope {
		if operation, ok := operations[name]; ok && operation.Mutating {
			writes = append(writes, name)
		}
	}
	return writes
}

func Permission(name string) string {
	return operations[name].Permission
}
