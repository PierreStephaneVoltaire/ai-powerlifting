from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Union, Literal

LoadSource = Literal["absolute", "rpe", "percentage", "unresolvable"]
LoadType = LoadSource
WeekStartDay = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

@dataclass
class TemplateLineage:
    applied_template_sk: str
    applied_at: str
    week_start_day: WeekStartDay
    start_date: str

@dataclass
class E1rmEstimate:
    value_kg: float
    method: Literal["manual", "ai_backfill", "logged"]
    basis: str
    confidence: Literal["high", "medium", "low"]
    set_at: str
    manually_overridden: bool

@dataclass
class AiTemplateEvaluation:
    stance: str
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    context_snapshot: Any

@dataclass
class TemplatePhase:
    name: str
    week_start: int
    week_end: int
    target_rpe_min: Optional[float] = None
    target_rpe_max: Optional[float] = None
    intent: str = ""

@dataclass
class TemplateExercise:
    name: str
    sets: int
    reps: int
    load_type: LoadType
    load_value: Optional[float] = None
    rpe_target: Optional[float] = None
    notes: str = ""
    glossary_id: Optional[str] = None

@dataclass
class TemplateSession:
    id: str
    week_number: int
    day_of_week: str
    day_index: int
    label: str
    exercises: List[TemplateExercise]

@dataclass
class GlossaryResolution:
    resolved: List[str]
    unresolved: List[str]
    auto_added: List[str]
    resolution_status: Literal["resolved", "partial", "unresolved"]

@dataclass
class TemplateMeta:
    name: str
    description: str
    estimated_weeks: int
    days_per_week: int
    created_at: str
    updated_at: str
    archived: bool = False
    source_filename: Optional[str] = None
    source_file_hash: Optional[str] = None
    derived_from_template_sk: Optional[str] = None
    derived_from_program_sk: Optional[str] = None
    ai_evaluation: Optional[AiTemplateEvaluation] = None

@dataclass
class Template:
    pk: str
    sk: str
    meta: TemplateMeta
    phases: List[TemplatePhase]
    sessions: List[TemplateSession]
    glossary_resolution: GlossaryResolution
    required_maxes: List[str]

@dataclass
class ImportWarning:
    type: str
    message: str
    severity: Literal["low", "medium", "high"]

@dataclass
class AiParseResult:
    phases: List[Any]
    sessions: List[Any]
    warnings: List[ImportWarning]
    raw_output: Optional[str] = None

@dataclass
class ConflictResolution:
    session_date: str
    action: Literal["skip", "overwrite", "merge"]

@dataclass
class ImportPending:
    pk: str
    sk: str
    import_id: str
    import_type: Literal["template", "session_import"]
    status: Literal["awaiting_review", "applied", "rejected"]
    source_filename: str
    source_file_hash: str
    uploaded_at: str
    expires_at: str
    ttl: int
    ai_parse_result: AiParseResult
    merge_strategy: Optional[Literal["append", "overwrite_future", "selective"]] = None
    conflict_resolutions: List[ConflictResolution] = field(default_factory=list)
    applied_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rejection_reason: Optional[str] = None
