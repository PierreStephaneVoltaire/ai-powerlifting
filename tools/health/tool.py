"""Health tool plugin — training program management and powerlifting tools.

Exports:
    get_tools()       → SDK Tool objects (side effect: register_tool() calls)
    get_schemas()     → snake_case name → JSON schema
    execute(name, args) → async dispatcher for non-agentic path
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

from tools.sdk_compat import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


# =============================================================================
# Initial Setup: Sync powerlifting datasets from S3 to sandbox
# =============================================================================

def _sync_powerlifting_datasets():
    import os
    import logging
    import threading
    from pathlib import Path

    if os.getenv("IF_DISABLE_POWERLIFTING_DATASET_SYNC") == "1" or os.getenv("IF_MCP_ALLOWED_TOOLS"):
        return

    def _sync_worker():
        try:
            import boto3
            from config import SANDBOX_PATH

            logger = logging.getLogger(__name__)
            bucket_name = os.getenv("POWERLIFTING_S3_BUCKET")
            if not bucket_name:
                logger.warning("Health Plugin: POWERLIFTING_S3_BUCKET env var not set, skipping dataset sync")
            else:
                prefix = "datasets/"
                sandbox_dir = Path(SANDBOX_PATH)
                sandbox_dir.mkdir(parents=True, exist_ok=True)

                logger.info(f"Health Plugin: [Background] Syncing powerlifting datasets from s3://{bucket_name}/{prefix} to {sandbox_dir}...")
                s3 = boto3.client('s3')
                response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        if key.endswith('.csv') and 'openpowerlifting' in key:
                            filename = os.path.basename(key)
                            dest_path = sandbox_dir / filename
                            if not dest_path.exists():
                                logger.info(f"Health Plugin: [Background] Downloading {filename}...")
                                s3.download_file(bucket_name, key, str(dest_path))
                    logger.info("Health Plugin: [Background] Powerlifting datasets sync complete")
                else:
                    logger.warning(f"Health Plugin: [Background] No powerlifting datasets found in s3://{bucket_name}/{prefix}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Health Plugin: [Background] Powerlifting dataset sync failed: {e}")

        # Always attempt to warm the DataFrame cache after sync (covers both fresh
        # downloads and restarts where files already exist on the PV).
        try:
            from powerlifting_stats import warm_cache
            warm_cache()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Health Plugin: [Background] warm_cache() failed: {e}")

    # Run sync in background thread to avoid blocking tool loading/app startup
    thread = threading.Thread(target=_sync_worker, daemon=True)
    thread.start()

_sync_powerlifting_datasets()


# =============================================================================
# Helpers (duplicated from agent/tools/base to avoid cross-dir imports)
# =============================================================================

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


def _sanitize_decimals(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _get_glossary_sync(table_name: str) -> list[dict]:
    """Fetch glossary from DynamoDB for the active health partition."""
    import boto3
    from core import _get_store

    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": _get_store().pk, "sk": "glossary#v1"})
    item = resp.get("Item")
    if not item:
        return []
    return _sanitize_decimals(item.get("exercises", []))


def _get_versioned_item_sync(table_name: str, pk: str, sk: str) -> dict | None:
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": pk, "sk": sk})
    item = resp.get("Item")
    if not item:
        return None
    return _sanitize_decimals(item)


# =============================================================================
# SDK Tool Classes (migrated from agent/tools/health_tools.py)
# =============================================================================

# --- health_get_program ---

class HealthGetProgramAction(Action):
    pass


class HealthGetProgramObservation(Observation):
    pass


class HealthGetProgramExecutor(ToolExecutor[HealthGetProgramAction, HealthGetProgramObservation]):
    def __call__(self, action: HealthGetProgramAction, conversation=None) -> HealthGetProgramObservation:
        from core import health_get_program
        result = _run_async(health_get_program())
        return HealthGetProgramObservation.from_text(_format_result(result))


class HealthGetProgramTool(ToolDefinition[HealthGetProgramAction, HealthGetProgramObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetProgramTool"]:
        return [cls(
            description=(
                "Get the full training program from DynamoDB. "
                "Returns the cached program dict with all sessions, phases, meta, and preferences."
            ),
            action_type=HealthGetProgramAction,
            observation_type=HealthGetProgramObservation,
            executor=HealthGetProgramExecutor(),
        )]


# --- health_setup_status ---

class HealthSetupStatusAction(Action):
    pass


class HealthSetupStatusObservation(Observation):
    pass


class HealthSetupStatusExecutor(ToolExecutor[HealthSetupStatusAction, HealthSetupStatusObservation]):
    def __call__(self, action: HealthSetupStatusAction, conversation=None) -> HealthSetupStatusObservation:
        from core import health_setup_status
        result = _run_async(health_setup_status())
        return HealthSetupStatusObservation.from_text(_format_result(result))


class HealthSetupStatusTool(ToolDefinition[HealthSetupStatusAction, HealthSetupStatusObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthSetupStatusTool"]:
        return [cls(
            description="Return no-data onboarding setup state for the active training data partition.",
            action_type=HealthSetupStatusAction,
            observation_type=HealthSetupStatusObservation,
            executor=HealthSetupStatusExecutor(),
        )]


# --- health_setup_initialize ---

class HealthSetupInitializeAction(Action):
    mode: str = Field(description="Initialization mode: blank, manual_sessions, or template")
    start_date: str = Field(description="Program start date (YYYY-MM-DD)")
    week_start_day: str = Field(description="Week start day, e.g. Monday")
    program_name: Optional[str] = Field(default=None, description="Optional program/block name")
    template_sk: Optional[str] = Field(default=None, description="Required when mode=template")
    maxes: Optional[Dict[str, float]] = Field(default=None, description="Optional maxes/e1RMs keyed by squat, bench, deadlift, or template glossary IDs")


class HealthSetupInitializeObservation(Observation):
    pass


class HealthSetupInitializeExecutor(ToolExecutor[HealthSetupInitializeAction, HealthSetupInitializeObservation]):
    def __call__(self, action: HealthSetupInitializeAction, conversation=None) -> HealthSetupInitializeObservation:
        from core import health_setup_initialize
        result = _run_async(health_setup_initialize(
            action.mode,
            action.start_date,
            action.week_start_day,
            action.program_name,
            action.template_sk,
            action.maxes,
        ))
        return HealthSetupInitializeObservation.from_text(_format_result(result))


class HealthSetupInitializeTool(ToolDefinition[HealthSetupInitializeAction, HealthSetupInitializeObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthSetupInitializeTool"]:
        return [cls(
            description="Initialize the first valid training block for a no-data user.",
            action_type=HealthSetupInitializeAction,
            observation_type=HealthSetupInitializeObservation,
            executor=HealthSetupInitializeExecutor(),
        )]


# --- health_comp_countdown ---

class HealthCompCountdownAction(Action):
    pass


class HealthCompCountdownObservation(Observation):
    pass


class HealthCompCountdownExecutor(ToolExecutor[HealthCompCountdownAction, HealthCompCountdownObservation]):
    def __call__(self, action: HealthCompCountdownAction, conversation=None) -> HealthCompCountdownObservation:
        from core import health_comp_countdown
        result = _run_async(health_comp_countdown())
        return HealthCompCountdownObservation.from_text(_format_result(result))


class HealthCompCountdownTool(ToolDefinition[HealthCompCountdownAction, HealthCompCountdownObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthCompCountdownTool"]:
        return [cls(
            description=(
                "Calculate competition countdown metrics. "
                "Returns days/weeks to competition, current week/phase, break status, and remaining sessions."
            ),
            action_type=HealthCompCountdownAction,
            observation_type=HealthCompCountdownObservation,
            executor=HealthCompCountdownExecutor(),
        )]


# --- health_update_session ---

class HealthUpdateSessionAction(Action):
    date: str = Field(description="ISO8601 date string (YYYY-MM-DD) of the session to update")
    patch: Dict[str, Any] = Field(
        description="Dict with session fields to update. Allowed keys: completed, session_rpe, body_weight_kg, session_notes, exercises"
    )


class HealthUpdateSessionObservation(Observation):
    pass


class HealthUpdateSessionExecutor(ToolExecutor[HealthUpdateSessionAction, HealthUpdateSessionObservation]):
    def __call__(self, action: HealthUpdateSessionAction, conversation=None) -> HealthUpdateSessionObservation:
        from core import health_update_session
        result = _run_async(health_update_session(action.date, action.patch))
        return HealthUpdateSessionObservation.from_text(_format_result(result))


class HealthUpdateSessionTool(ToolDefinition[HealthUpdateSessionAction, HealthUpdateSessionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateSessionTool"]:
        return [cls(
            description=(
                "Update a training session by date. "
                "Use to log session completion, RPE, body weight, notes, or exercise details."
            ),
            action_type=HealthUpdateSessionAction,
            observation_type=HealthUpdateSessionObservation,
            executor=HealthUpdateSessionExecutor(),
        )]


# --- health_new_version ---

class HealthNewVersionAction(Action):
    change_reason: str = Field(description="Human-readable reason for the version change")
    patches: List[Dict[str, Any]] = Field(
        description="List of patches, each with 'path' (e.g., 'sessions[0].exercises[1].kg') and 'value' keys"
    )


class HealthNewVersionObservation(Observation):
    pass


class HealthNewVersionExecutor(ToolExecutor[HealthNewVersionAction, HealthNewVersionObservation]):
    def __call__(self, action: HealthNewVersionAction, conversation=None) -> HealthNewVersionObservation:
        from core import health_new_version
        result = _run_async(health_new_version(action.change_reason, action.patches))
        return HealthNewVersionObservation.from_text(_format_result(result))


class HealthNewVersionTool(ToolDefinition[HealthNewVersionAction, HealthNewVersionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthNewVersionTool"]:
        return [cls(
            description=(
                "Create a new major version of the training program with patches. "
                "Use for significant program changes that warrant version tracking."
            ),
            action_type=HealthNewVersionAction,
            observation_type=HealthNewVersionObservation,
            executor=HealthNewVersionExecutor(),
        )]


# --- kg_to_lb ---

class KgToLbAction(Action):
    kg: float = Field(description="Weight in kilograms")


class KgToLbObservation(Observation):
    pass


class KgToLbExecutor(ToolExecutor[KgToLbAction, KgToLbObservation]):
    def __call__(self, action: KgToLbAction, conversation=None) -> KgToLbObservation:
        from core import kg_to_lb
        result = kg_to_lb(action.kg)
        return KgToLbObservation.from_text(_format_result(result))


class KgToLbTool(ToolDefinition[KgToLbAction, KgToLbObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["KgToLbTool"]:
        return [cls(
            description="Convert kilograms to pounds. Returns both kg and lb values.",
            action_type=KgToLbAction,
            observation_type=KgToLbObservation,
            executor=KgToLbExecutor(),
        )]


# --- lb_to_kg ---

class LbToKgAction(Action):
    lb: float = Field(description="Weight in pounds")


class LbToKgObservation(Observation):
    pass


class LbToKgExecutor(ToolExecutor[LbToKgAction, LbToKgObservation]):
    def __call__(self, action: LbToKgAction, conversation=None) -> LbToKgObservation:
        from core import lb_to_kg
        result = lb_to_kg(action.lb)
        return LbToKgObservation.from_text(_format_result(result))


class LbToKgTool(ToolDefinition[LbToKgAction, LbToKgObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["LbToKgTool"]:
        return [cls(
            description="Convert pounds to kilograms. Returns both lb and kg values.",
            action_type=LbToKgAction,
            observation_type=LbToKgObservation,
            executor=LbToKgExecutor(),
        )]


# --- ipf_weight_classes ---

class IpfWeightClassesAction(Action):
    sex: str = Field(description="Sex for weight classes: 'M' or 'F'")


class IpfWeightClassesObservation(Observation):
    pass


class IpfWeightClassesExecutor(ToolExecutor[IpfWeightClassesAction, IpfWeightClassesObservation]):
    def __call__(self, action: IpfWeightClassesAction, conversation=None) -> IpfWeightClassesObservation:
        from core import ipf_weight_classes
        result = ipf_weight_classes(action.sex)
        return IpfWeightClassesObservation.from_text(_format_result(result))


class IpfWeightClassesTool(ToolDefinition[IpfWeightClassesAction, IpfWeightClassesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["IpfWeightClassesTool"]:
        return [cls(
            description=(
                "Get IPF weight classes for men or women. "
                "Returns weight classes in kg and the operator's current weight class if available."
            ),
            action_type=IpfWeightClassesAction,
            observation_type=IpfWeightClassesObservation,
            executor=IpfWeightClassesExecutor(),
        )]


# --- pct_of_max ---

class PctOfMaxAction(Action):
    max_kg: float = Field(description="Maximum weight in kilograms")
    pct: float = Field(description="Percentage (0-150, not 0-1). E.g., 85 for 85%")


class PctOfMaxObservation(Observation):
    pass


class PctOfMaxExecutor(ToolExecutor[PctOfMaxAction, PctOfMaxObservation]):
    def __call__(self, action: PctOfMaxAction, conversation=None) -> PctOfMaxObservation:
        from core import pct_of_max
        result = pct_of_max(action.max_kg, action.pct)
        return PctOfMaxObservation.from_text(_format_result(result))


class PctOfMaxTool(ToolDefinition[PctOfMaxAction, PctOfMaxObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["PctOfMaxTool"]:
        return [cls(
            description=(
                "Calculate percentage of max weight. "
                "Returns raw kg, rounded to nearest 2.5kg, and lb conversion."
            ),
            action_type=PctOfMaxAction,
            observation_type=PctOfMaxObservation,
            executor=PctOfMaxExecutor(),
        )]


# --- calculate_attempts ---

class CalculateAttemptsAction(Action):
    lift: str = Field(description="Lift type: 'squat', 'bench', or 'deadlift'")
    opener_kg: float = Field(description="First attempt weight in kg")
    j1_override: Optional[float] = Field(default=None, description="Override jump 1 from program prefs (kg)")
    j2_override: Optional[float] = Field(default=None, description="Override jump 2 from program prefs (kg)")
    last_felt: Optional[str] = Field(default=None, description="If 'hard', halve j2 for conservative third attempt")


class CalculateAttemptsObservation(Observation):
    pass


class CalculateAttemptsExecutor(ToolExecutor[CalculateAttemptsAction, CalculateAttemptsObservation]):
    def __call__(self, action: CalculateAttemptsAction, conversation=None) -> CalculateAttemptsObservation:
        from core import calculate_attempts
        result = _run_async(calculate_attempts(
            lift=action.lift,
            opener_kg=action.opener_kg,
            j1_override=action.j1_override,
            j2_override=action.j2_override,
            last_felt=action.last_felt,
        ))
        return CalculateAttemptsObservation.from_text(_format_result(result))


class CalculateAttemptsTool(ToolDefinition[CalculateAttemptsAction, CalculateAttemptsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["CalculateAttemptsTool"]:
        return [cls(
            description=(
                "Calculate competition attempts based on opener and program preferences. "
                "Returns three attempts with jumps used and any warnings."
            ),
            action_type=CalculateAttemptsAction,
            observation_type=CalculateAttemptsObservation,
            executor=CalculateAttemptsExecutor(),
        )]


# --- health_rag_search ---

class HealthRagSearchAction(Action):
    query: str = Field(description="Search query for health documents")
    n_results: int = Field(default=4, description="Number of results to return")


class HealthRagSearchObservation(Observation):
    pass


class HealthRagSearchExecutor(ToolExecutor[HealthRagSearchAction, HealthRagSearchObservation]):
    def __call__(self, action: HealthRagSearchAction, conversation=None) -> HealthRagSearchObservation:
        from core import health_rag_search
        result = _run_async(health_rag_search(action.query, action.n_results))
        return HealthRagSearchObservation.from_text(_format_result(result))


class HealthRagSearchTool(ToolDefinition[HealthRagSearchAction, HealthRagSearchObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthRagSearchTool"]:
        return [cls(
            description=(
                "Search health documents (IPF rulebook, anti-doping list, supplement info) using semantic search. "
                "Use for questions about rules, banned substances, or supplement guidance."
            ),
            action_type=HealthRagSearchAction,
            observation_type=HealthRagSearchObservation,
            executor=HealthRagSearchExecutor(),
        )]


# --- health_get_competition ---

class HealthGetCompetitionAction(Action):
    date: str = Field(description="Competition date (YYYY-MM-DD)")


class HealthGetCompetitionObservation(Observation):
    pass


class HealthGetCompetitionExecutor(ToolExecutor[HealthGetCompetitionAction, HealthGetCompetitionObservation]):
    def __call__(self, action: HealthGetCompetitionAction, conversation=None) -> HealthGetCompetitionObservation:
        from core import health_get_competition
        result = _run_async(health_get_competition(action.date))
        return HealthGetCompetitionObservation.from_text(_format_result(result))


class HealthGetCompetitionTool(ToolDefinition[HealthGetCompetitionAction, HealthGetCompetitionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetCompetitionTool"]:
        return [cls(
            description=(
                "Load a specific competition by date. "
                "Returns full competition object including targets, between_comp_plan, and comp_day_protocol."
            ),
            action_type=HealthGetCompetitionAction,
            observation_type=HealthGetCompetitionObservation,
            executor=HealthGetCompetitionExecutor(),
        )]


# --- health_list_competitions ---

class HealthListCompetitionsAction(Action):
    pass


class HealthListCompetitionsObservation(Observation):
    pass


class HealthListCompetitionsExecutor(ToolExecutor[HealthListCompetitionsAction, HealthListCompetitionsObservation]):
    def __call__(self, action: HealthListCompetitionsAction, conversation=None) -> HealthListCompetitionsObservation:
        from core import health_list_competitions
        result = _run_async(health_list_competitions())
        return HealthListCompetitionsObservation.from_text(_format_result(result))


class HealthListCompetitionsTool(ToolDefinition[HealthListCompetitionsAction, HealthListCompetitionsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthListCompetitionsTool"]:
        return [cls(
            description=(
                "List all competitions with summary info. "
                "Returns array of {name, date, status, weight_class_kg, federation}."
            ),
            action_type=HealthListCompetitionsAction,
            observation_type=HealthListCompetitionsObservation,
            executor=HealthListCompetitionsExecutor(),
        )]


# --- health_get_diet_notes ---

class HealthGetDietNotesAction(Action):
    start_date: Optional[str] = Field(default=None, description="Optional start of date range (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="Optional end of date range (YYYY-MM-DD)")


class HealthGetDietNotesObservation(Observation):
    pass


class HealthGetDietNotesExecutor(ToolExecutor[HealthGetDietNotesAction, HealthGetDietNotesObservation]):
    def __call__(self, action: HealthGetDietNotesAction, conversation=None) -> HealthGetDietNotesObservation:
        from core import health_get_diet_notes
        result = _run_async(health_get_diet_notes(action.start_date, action.end_date))
        return HealthGetDietNotesObservation.from_text(_format_result(result))


class HealthGetDietNotesTool(ToolDefinition[HealthGetDietNotesAction, HealthGetDietNotesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetDietNotesTool"]:
        return [cls(
            description=(
                "Get diet notes, optionally filtered by date range. "
                "Returns array of {date, notes} sorted by date descending."
            ),
            action_type=HealthGetDietNotesAction,
            observation_type=HealthGetDietNotesObservation,
            executor=HealthGetDietNotesExecutor(),
        )]


# --- health_get_session ---

class HealthGetSessionAction(Action):
    date: str = Field(description="Session date (YYYY-MM-DD)")


class HealthGetSessionObservation(Observation):
    pass


class HealthGetSessionExecutor(ToolExecutor[HealthGetSessionAction, HealthGetSessionObservation]):
    def __call__(self, action: HealthGetSessionAction, conversation=None) -> HealthGetSessionObservation:
        from core import health_get_session
        result = _run_async(health_get_session(action.date))
        return HealthGetSessionObservation.from_text(_format_result(result))


class HealthGetSessionTool(ToolDefinition[HealthGetSessionAction, HealthGetSessionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetSessionTool"]:
        return [cls(
            description=(
                "Load a single training session by date. "
                "Returns session with exercises and resolved phase object."
            ),
            action_type=HealthGetSessionAction,
            observation_type=HealthGetSessionObservation,
            executor=HealthGetSessionExecutor(),
        )]


# --- health_get_sessions_range ---

class HealthGetSessionsRangeAction(Action):
    start_date: str = Field(description="Start of date range (YYYY-MM-DD)")
    end_date: str = Field(description="End of date range (YYYY-MM-DD)")


class HealthGetSessionsRangeObservation(Observation):
    pass


class HealthGetSessionsRangeExecutor(ToolExecutor[HealthGetSessionsRangeAction, HealthGetSessionsRangeObservation]):
    def __call__(self, action: HealthGetSessionsRangeAction, conversation=None) -> HealthGetSessionsRangeObservation:
        from core import health_get_sessions_range
        result = _run_async(health_get_sessions_range(action.start_date, action.end_date))
        return HealthGetSessionsRangeObservation.from_text(_format_result(result))


class HealthGetSessionsRangeTool(ToolDefinition[HealthGetSessionsRangeAction, HealthGetSessionsRangeObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetSessionsRangeTool"]:
        return [cls(
            description=(
                "Load training sessions within a date range. "
                "Returns array of sessions in date order, each with resolved phase."
            ),
            action_type=HealthGetSessionsRangeAction,
            observation_type=HealthGetSessionsRangeObservation,
            executor=HealthGetSessionsRangeExecutor(),
        )]


# --- health_get_supplements ---

class HealthGetSupplementsAction(Action):
    pass


class HealthGetSupplementsObservation(Observation):
    pass


class HealthGetSupplementsExecutor(ToolExecutor[HealthGetSupplementsAction, HealthGetSupplementsObservation]):
    def __call__(self, action: HealthGetSupplementsAction, conversation=None) -> HealthGetSupplementsObservation:
        from core import health_get_supplements
        result = _run_async(health_get_supplements())
        return HealthGetSupplementsObservation.from_text(_format_result(result))


class HealthGetSupplementsTool(ToolDefinition[HealthGetSupplementsAction, HealthGetSupplementsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetSupplementsTool"]:
        return [cls(
            description=(
                "Load supplements and supplement phases. "
                "Returns {supplements: [...], supplement_phases: [...]}."
            ),
            action_type=HealthGetSupplementsAction,
            observation_type=HealthGetSupplementsObservation,
            executor=HealthGetSupplementsExecutor(),
        )]


# --- health_get_meta ---

class HealthGetMetaAction(Action):
    pass


class HealthGetMetaObservation(Observation):
    pass


class HealthGetMetaExecutor(ToolExecutor[HealthGetMetaAction, HealthGetMetaObservation]):
    def __call__(self, action: HealthGetMetaAction, conversation=None) -> HealthGetMetaObservation:
        from core import health_get_meta
        result = _run_async(health_get_meta())
        return HealthGetMetaObservation.from_text(_format_result(result))


class HealthGetMetaTool(ToolDefinition[HealthGetMetaAction, HealthGetMetaObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetMetaTool"]:
        return [cls(
            description=(
                "Get program metadata: comp_date, program_start, targets (squat/bench/deadlift/total), "
                "weight_class_kg, version, training_notes, change_log. "
                "Use this instead of health_get_program when you only need program-level info."
            ),
            action_type=HealthGetMetaAction,
            observation_type=HealthGetMetaObservation,
            executor=HealthGetMetaExecutor(),
        )]


# --- health_get_phases ---

class HealthGetPhasesAction(Action):
    pass


class HealthGetPhasesObservation(Observation):
    pass


class HealthGetPhasesExecutor(ToolExecutor[HealthGetPhasesAction, HealthGetPhasesObservation]):
    def __call__(self, action: HealthGetPhasesAction, conversation=None) -> HealthGetPhasesObservation:
        from core import health_get_phases
        result = _run_async(health_get_phases())
        return HealthGetPhasesObservation.from_text(_format_result(result))


class HealthGetPhasesTool(ToolDefinition[HealthGetPhasesAction, HealthGetPhasesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetPhasesTool"]:
        return [cls(
            description=(
                "Get training phases (name, start_week, end_week, intent). "
                "Use to understand the program structure without loading all sessions."
            ),
            action_type=HealthGetPhasesAction,
            observation_type=HealthGetPhasesObservation,
            executor=HealthGetPhasesExecutor(),
        )]


# --- health_get_current_maxes ---

class HealthGetCurrentMaxesAction(Action):
    pass


class HealthGetCurrentMaxesObservation(Observation):
    pass


class HealthGetCurrentMaxesExecutor(ToolExecutor[HealthGetCurrentMaxesAction, HealthGetCurrentMaxesObservation]):
    def __call__(self, action: HealthGetCurrentMaxesAction, conversation=None) -> HealthGetCurrentMaxesObservation:
        from core import health_get_current_maxes
        result = _run_async(health_get_current_maxes())
        return HealthGetCurrentMaxesObservation.from_text(_format_result(result))


class HealthGetCurrentMaxesTool(ToolDefinition[HealthGetCurrentMaxesAction, HealthGetCurrentMaxesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetCurrentMaxesTool"]:
        return [cls(
            description=(
                "Get current competition maxes in kg: {squat, bench, deadlift}. "
                "Use for percentage calculations or attempt planning without loading the full program."
            ),
            action_type=HealthGetCurrentMaxesAction,
            observation_type=HealthGetCurrentMaxesObservation,
            executor=HealthGetCurrentMaxesExecutor(),
        )]


# --- health_get_goals ---

class HealthGetGoalsAction(Action):
    pass


class HealthGetGoalsObservation(Observation):
    pass


class HealthGetGoalsExecutor(ToolExecutor[HealthGetGoalsAction, HealthGetGoalsObservation]):
    def __call__(self, action: HealthGetGoalsAction, conversation=None) -> HealthGetGoalsObservation:
        from core import health_get_goals
        result = _run_async(health_get_goals())
        return HealthGetGoalsObservation.from_text(_format_result(result))


class HealthGetGoalsTool(ToolDefinition[HealthGetGoalsAction, HealthGetGoalsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetGoalsTool"]:
        return [cls(
            description=(
                "Get the explicit goals for the current training block. "
                "Returns the full goals array used by goal-aware program evaluation."
            ),
            action_type=HealthGetGoalsAction,
            observation_type=HealthGetGoalsObservation,
            executor=HealthGetGoalsExecutor(),
        )]


# --- health_update_goals ---

class HealthUpdateGoalsAction(Action):
    goals: List[Dict[str, Any]] = Field(
        description="Complete explicit goals array to write onto the current program block"
    )


class HealthUpdateGoalsObservation(Observation):
    pass


class HealthUpdateGoalsExecutor(ToolExecutor[HealthUpdateGoalsAction, HealthUpdateGoalsObservation]):
    def __call__(self, action: HealthUpdateGoalsAction, conversation=None) -> HealthUpdateGoalsObservation:
        from core import health_update_goals
        result = _run_async(health_update_goals(action.goals))
        return HealthUpdateGoalsObservation.from_text(_format_result(result))


class HealthUpdateGoalsTool(ToolDefinition[HealthUpdateGoalsAction, HealthUpdateGoalsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateGoalsTool"]:
        return [cls(
            description=(
                "Replace the current block's explicit goals array. "
                "This writes a new minor program version and validates goal types, priorities, dates, and strategy modes."
            ),
            action_type=HealthUpdateGoalsAction,
            observation_type=HealthUpdateGoalsObservation,
            executor=HealthUpdateGoalsExecutor(),
        )]


# --- health_get_federation_library ---

class HealthGetFederationLibraryAction(Action):
    pass


class HealthGetFederationLibraryObservation(Observation):
    pass


class HealthGetFederationLibraryExecutor(ToolExecutor[HealthGetFederationLibraryAction, HealthGetFederationLibraryObservation]):
    def __call__(self, action: HealthGetFederationLibraryAction, conversation=None) -> HealthGetFederationLibraryObservation:
        from core import health_get_federation_library
        result = _run_async(health_get_federation_library())
        return HealthGetFederationLibraryObservation.from_text(_format_result(result))


class HealthGetFederationLibraryTool(ToolDefinition[HealthGetFederationLibraryAction, HealthGetFederationLibraryObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetFederationLibraryTool"]:
        return [cls(
            description=(
                "Get the shared federation library, including federations and qualification standards. "
                "Use this when comparing goals or competitions against qualifying totals."
            ),
            action_type=HealthGetFederationLibraryAction,
            observation_type=HealthGetFederationLibraryObservation,
            executor=HealthGetFederationLibraryExecutor(),
        )]


# --- health_update_federation_library ---

class HealthUpdateFederationLibraryAction(Action):
    federations: List[Dict[str, Any]] = Field(description="Complete federation records array")
    qualification_standards: List[Dict[str, Any]] = Field(
        description="Complete qualification standards array linked to the federation ids above"
    )


class HealthUpdateFederationLibraryObservation(Observation):
    pass


class HealthUpdateFederationLibraryExecutor(ToolExecutor[HealthUpdateFederationLibraryAction, HealthUpdateFederationLibraryObservation]):
    def __call__(self, action: HealthUpdateFederationLibraryAction, conversation=None) -> HealthUpdateFederationLibraryObservation:
        from core import health_update_federation_library
        result = _run_async(health_update_federation_library({
            "federations": action.federations,
            "qualification_standards": action.qualification_standards,
        }))
        return HealthUpdateFederationLibraryObservation.from_text(_format_result(result))


class HealthUpdateFederationLibraryTool(ToolDefinition[HealthUpdateFederationLibraryAction, HealthUpdateFederationLibraryObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateFederationLibraryTool"]:
        return [cls(
            description=(
                "Replace the shared federation library document. "
                "Validates federation ids and qualification-standard metadata before writing the new record."
            ),
            action_type=HealthUpdateFederationLibraryAction,
            observation_type=HealthUpdateFederationLibraryObservation,
            executor=HealthUpdateFederationLibraryExecutor(),
        )]


# --- health_get_operator_prefs ---

class HealthGetOperatorPrefsAction(Action):
    pass


class HealthGetOperatorPrefsObservation(Observation):
    pass


class HealthGetOperatorPrefsExecutor(ToolExecutor[HealthGetOperatorPrefsAction, HealthGetOperatorPrefsObservation]):
    def __call__(self, action: HealthGetOperatorPrefsAction, conversation=None) -> HealthGetOperatorPrefsObservation:
        from core import health_get_operator_prefs
        result = _run_async(health_get_operator_prefs())
        return HealthGetOperatorPrefsObservation.from_text(_format_result(result))


class HealthGetOperatorPrefsTool(ToolDefinition[HealthGetOperatorPrefsAction, HealthGetOperatorPrefsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetOperatorPrefsTool"]:
        return [cls(
            description=(
                "Get operator preferences including attempt_jumps per lift (j1, j2 in kg). "
                "Use when calculating competition attempts or checking preferred jump sizes."
            ),
            action_type=HealthGetOperatorPrefsAction,
            observation_type=HealthGetOperatorPrefsObservation,
            executor=HealthGetOperatorPrefsExecutor(),
        )]


# --- health_get_breaks ---

class HealthGetBreaksAction(Action):
    pass


class HealthGetBreaksObservation(Observation):
    pass


class HealthGetBreaksExecutor(ToolExecutor[HealthGetBreaksAction, HealthGetBreaksObservation]):
    def __call__(self, action: HealthGetBreaksAction, conversation=None) -> HealthGetBreaksObservation:
        from core import health_get_breaks
        result = _run_async(health_get_breaks())
        return HealthGetBreaksObservation.from_text(_format_result(result))


class HealthGetBreaksTool(ToolDefinition[HealthGetBreaksAction, HealthGetBreaksObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetBreaksTool"]:
        return [cls(
            description=(
                "Get scheduled break/deload periods: [{start, end}, ...]. "
                "Use to check if a date falls in a rest week or when the next break is."
            ),
            action_type=HealthGetBreaksAction,
            observation_type=HealthGetBreaksObservation,
            executor=HealthGetBreaksExecutor(),
        )]


# --- days_until ---

class DaysUntilAction(Action):
    target_date: str = Field(description="Target date (YYYY-MM-DD)")
    label: str = Field(default="target", description="Human label for the milestone, e.g. 'comp', 'deload'")


class DaysUntilObservation(Observation):
    pass


class DaysUntilExecutor(ToolExecutor[DaysUntilAction, DaysUntilObservation]):
    def __call__(self, action: DaysUntilAction, conversation=None) -> DaysUntilObservation:
        from core import days_until
        result = _run_async(days_until(action.target_date, action.label))
        return DaysUntilObservation.from_text(_format_result(result))


class DaysUntilTool(ToolDefinition[DaysUntilAction, DaysUntilObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["DaysUntilTool"]:
        return [cls(
            description=(
                "Calculate days and weeks until (or since) a target date. "
                "Returns days_remaining, weeks_remaining, today, is_past."
            ),
            action_type=DaysUntilAction,
            observation_type=DaysUntilObservation,
            executor=DaysUntilExecutor(),
        )]


# --- health_update_competition ---

class HealthUpdateCompetitionAction(Action):
    date: str = Field(description="Competition date to update (YYYY-MM-DD)")
    patch: Dict[str, Any] = Field(
        description="Fields to update (targets, status, notes, between_comp_plan, comp_day_protocol, etc.)"
    )


class HealthUpdateCompetitionObservation(Observation):
    pass


class HealthUpdateCompetitionExecutor(ToolExecutor[HealthUpdateCompetitionAction, HealthUpdateCompetitionObservation]):
    def __call__(self, action: HealthUpdateCompetitionAction, conversation=None) -> HealthUpdateCompetitionObservation:
        from core import health_update_competition
        result = _run_async(health_update_competition(action.date, action.patch))
        return HealthUpdateCompetitionObservation.from_text(_format_result(result))


class HealthUpdateCompetitionTool(ToolDefinition[HealthUpdateCompetitionAction, HealthUpdateCompetitionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateCompetitionTool"]:
        return [cls(
            description=(
                "Update a competition by date. Creates a new minor program version. "
                "Use to update targets, status, notes, between_comp_plan, or comp_day_protocol."
            ),
            action_type=HealthUpdateCompetitionAction,
            observation_type=HealthUpdateCompetitionObservation,
            executor=HealthUpdateCompetitionExecutor(),
        )]


# --- health_snapshot_competition_projection ---

class HealthSnapshotCompetitionProjectionAction(Action):
    date: str = Field(description="Snapshot date (YYYY-MM-DD). Competitions on date + 7 days are considered.")
    version: str = Field(default="current", description="Program version to update")
    allow_retrospective: bool = Field(
        default=False,
        description="Allow backfilling a missing snapshot for a completed competition",
    )


class HealthSnapshotCompetitionProjectionObservation(Observation):
    pass


class HealthSnapshotCompetitionProjectionExecutor(ToolExecutor[HealthSnapshotCompetitionProjectionAction, HealthSnapshotCompetitionProjectionObservation]):
    def __call__(self, action: HealthSnapshotCompetitionProjectionAction, conversation=None) -> HealthSnapshotCompetitionProjectionObservation:
        from core import health_snapshot_competition_projection
        result = _run_async(health_snapshot_competition_projection(action.date, action.version, action.allow_retrospective))
        return HealthSnapshotCompetitionProjectionObservation.from_text(_format_result(result))


class HealthSnapshotCompetitionProjectionTool(ToolDefinition[HealthSnapshotCompetitionProjectionAction, HealthSnapshotCompetitionProjectionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthSnapshotCompetitionProjectionTool"]:
        return [cls(
            description=(
                "Snapshot projected competition maxes 7 days before a meet. "
                "Use allow_retrospective=true to backfill a missed snapshot."
            ),
            action_type=HealthSnapshotCompetitionProjectionAction,
            observation_type=HealthSnapshotCompetitionProjectionObservation,
            executor=HealthSnapshotCompetitionProjectionExecutor(),
        )]


# --- health_complete_competition ---

class HealthCompleteCompetitionAction(Action):
    date: str = Field(description="Competition date to complete (YYYY-MM-DD)")
    results: Dict[str, Any] = Field(description="Best successful lift attempts and total")
    body_weight_kg: float = Field(description="Official weigh-in bodyweight in kg")
    post_meet_report: Optional[Dict[str, Any]] = Field(default=None, description="Optional structured post-meet attempt and context report")
    version: str = Field(default="current", description="Program version to update")
    allow_retrospective: bool = Field(
        default=True,
        description="Backfill a missing T-1 snapshot if it was not captured before completion",
    )


class HealthCompleteCompetitionObservation(Observation):
    pass


class HealthCompleteCompetitionExecutor(ToolExecutor[HealthCompleteCompetitionAction, HealthCompleteCompetitionObservation]):
    def __call__(self, action: HealthCompleteCompetitionAction, conversation=None) -> HealthCompleteCompetitionObservation:
        from core import health_complete_competition
        result = _run_async(
            health_complete_competition(
                action.date,
                action.results,
                action.body_weight_kg,
                action.version,
                action.allow_retrospective,
                action.post_meet_report,
            )
        )
        return HealthCompleteCompetitionObservation.from_text(_format_result(result))


class HealthCompleteCompetitionTool(ToolDefinition[HealthCompleteCompetitionAction, HealthCompleteCompetitionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthCompleteCompetitionTool"]:
        return [cls(
            description=(
                "Mark a competition as completed, store results, and compute PRR from the pre-competition snapshot."
            ),
            action_type=HealthCompleteCompetitionAction,
            observation_type=HealthCompleteCompetitionObservation,
            executor=HealthCompleteCompetitionExecutor(),
        )]


# --- health_update_diet_note ---

class HealthUpdateDietNoteAction(Action):
    date: str = Field(description="Date for the diet note (YYYY-MM-DD)")
    notes: str = Field(description="The diet notes content (replaces existing)")


class HealthUpdateDietNoteObservation(Observation):
    pass


class HealthUpdateDietNoteExecutor(ToolExecutor[HealthUpdateDietNoteAction, HealthUpdateDietNoteObservation]):
    def __call__(self, action: HealthUpdateDietNoteAction, conversation=None) -> HealthUpdateDietNoteObservation:
        from core import health_update_diet_note
        result = _run_async(health_update_diet_note(action.date, action.notes))
        return HealthUpdateDietNoteObservation.from_text(_format_result(result))


class HealthUpdateDietNoteTool(ToolDefinition[HealthUpdateDietNoteAction, HealthUpdateDietNoteObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateDietNoteTool"]:
        return [cls(
            description=(
                "Update or create a diet note for a specific date. "
                "Creates a new minor program version. Replaces existing content."
            ),
            action_type=HealthUpdateDietNoteAction,
            observation_type=HealthUpdateDietNoteObservation,
            executor=HealthUpdateDietNoteExecutor(),
        )]


# --- health_update_supplements ---

class HealthUpdateSupplementsAction(Action):
    patch: Dict[str, Any] = Field(
        description='{"supplements": [...]} or {"supplement_phases": [...]} or both'
    )


class HealthUpdateSupplementsObservation(Observation):
    pass


class HealthUpdateSupplementsExecutor(ToolExecutor[HealthUpdateSupplementsAction, HealthUpdateSupplementsObservation]):
    def __call__(self, action: HealthUpdateSupplementsAction, conversation=None) -> HealthUpdateSupplementsObservation:
        from core import health_update_supplements
        result = _run_async(health_update_supplements(action.patch))
        return HealthUpdateSupplementsObservation.from_text(_format_result(result))


class HealthUpdateSupplementsTool(ToolDefinition[HealthUpdateSupplementsAction, HealthUpdateSupplementsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateSupplementsTool"]:
        return [cls(
            description=(
                "Update supplements or supplement phases. "
                "Creates a new minor program version."
            ),
            action_type=HealthUpdateSupplementsAction,
            observation_type=HealthUpdateSupplementsObservation,
            executor=HealthUpdateSupplementsExecutor(),
        )]


# --- health_create_session ---

class HealthCreateSessionAction(Action):
    date: str = Field(description="Session date (YYYY-MM-DD)")
    day: str = Field(description="Day label e.g. 'Monday'")
    week_number: int = Field(description="Training week number")
    exercises: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional list of exercises {name, sets, reps, kg, rpe, notes}")
    session_notes: str = Field(default="", description="Optional session notes")


class HealthCreateSessionObservation(Observation):
    pass


class HealthCreateSessionExecutor(ToolExecutor[HealthCreateSessionAction, HealthCreateSessionObservation]):
    def __call__(self, action: HealthCreateSessionAction, conversation=None) -> HealthCreateSessionObservation:
        from core import health_create_session
        result = _run_async(health_create_session(action.date, action.day, action.week_number, action.exercises, action.session_notes))
        return HealthCreateSessionObservation.from_text(_format_result(result))


class HealthCreateSessionTool(ToolDefinition[HealthCreateSessionAction, HealthCreateSessionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthCreateSessionTool"]:
        return [cls(
            description="Create a new training session. Requires date, day label, and week number. Optionally include exercises.",
            action_type=HealthCreateSessionAction,
            observation_type=HealthCreateSessionObservation,
            executor=HealthCreateSessionExecutor(),
        )]


# --- health_delete_session ---

class HealthDeleteSessionAction(Action):
    date: str = Field(description="Session date to delete (YYYY-MM-DD)")


class HealthDeleteSessionObservation(Observation):
    pass


class HealthDeleteSessionExecutor(ToolExecutor[HealthDeleteSessionAction, HealthDeleteSessionObservation]):
    def __call__(self, action: HealthDeleteSessionAction, conversation=None) -> HealthDeleteSessionObservation:
        from core import health_delete_session
        result = _run_async(health_delete_session(action.date))
        return HealthDeleteSessionObservation.from_text(_format_result(result))


class HealthDeleteSessionTool(ToolDefinition[HealthDeleteSessionAction, HealthDeleteSessionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthDeleteSessionTool"]:
        return [cls(
            description="Delete a training session by date. Cannot be undone.",
            action_type=HealthDeleteSessionAction,
            observation_type=HealthDeleteSessionObservation,
            executor=HealthDeleteSessionExecutor(),
        )]


# --- health_reschedule_session ---

class HealthRescheduleSessionAction(Action):
    old_date: str = Field(description="Current session date (YYYY-MM-DD)")
    new_date: str = Field(description="Target date to move to (YYYY-MM-DD)")


class HealthRescheduleSessionObservation(Observation):
    pass


class HealthRescheduleSessionExecutor(ToolExecutor[HealthRescheduleSessionAction, HealthRescheduleSessionObservation]):
    def __call__(self, action: HealthRescheduleSessionAction, conversation=None) -> HealthRescheduleSessionObservation:
        from core import health_reschedule_session
        result = _run_async(health_reschedule_session(action.old_date, action.new_date))
        return HealthRescheduleSessionObservation.from_text(_format_result(result))


class HealthRescheduleSessionTool(ToolDefinition[HealthRescheduleSessionAction, HealthRescheduleSessionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthRescheduleSessionTool"]:
        return [cls(
            description="Move a training session to a different date.",
            action_type=HealthRescheduleSessionAction,
            observation_type=HealthRescheduleSessionObservation,
            executor=HealthRescheduleSessionExecutor(),
        )]


# --- health_add_exercise ---

class HealthAddExerciseAction(Action):
    date: str = Field(description="Session date (YYYY-MM-DD)")
    exercise: Dict[str, Any] = Field(description="Exercise dict: {name (required), sets, reps, kg, rpe, notes}")


class HealthAddExerciseObservation(Observation):
    pass


class HealthAddExerciseExecutor(ToolExecutor[HealthAddExerciseAction, HealthAddExerciseObservation]):
    def __call__(self, action: HealthAddExerciseAction, conversation=None) -> HealthAddExerciseObservation:
        from core import health_add_exercise
        result = _run_async(health_add_exercise(action.date, action.exercise))
        return HealthAddExerciseObservation.from_text(_format_result(result))


class HealthAddExerciseTool(ToolDefinition[HealthAddExerciseAction, HealthAddExerciseObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthAddExerciseTool"]:
        return [cls(
            description="Add an exercise to a training session. Provide the session date and exercise dict {name, sets, reps, kg, rpe, notes}.",
            action_type=HealthAddExerciseAction,
            observation_type=HealthAddExerciseObservation,
            executor=HealthAddExerciseExecutor(),
        )]


# --- health_remove_exercise ---

class HealthRemoveExerciseAction(Action):
    date: str = Field(description="Session date (YYYY-MM-DD)")
    exercise_index: int = Field(description="Zero-based index of the exercise to remove")


class HealthRemoveExerciseObservation(Observation):
    pass


class HealthRemoveExerciseExecutor(ToolExecutor[HealthRemoveExerciseAction, HealthRemoveExerciseObservation]):
    def __call__(self, action: HealthRemoveExerciseAction, conversation=None) -> HealthRemoveExerciseObservation:
        from core import health_remove_exercise
        result = _run_async(health_remove_exercise(action.date, action.exercise_index))
        return HealthRemoveExerciseObservation.from_text(_format_result(result))


class HealthRemoveExerciseTool(ToolDefinition[HealthRemoveExerciseAction, HealthRemoveExerciseObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthRemoveExerciseTool"]:
        return [cls(
            description="Remove an exercise from a session by its zero-based index. Fetch the session first to confirm the correct index.",
            action_type=HealthRemoveExerciseAction,
            observation_type=HealthRemoveExerciseObservation,
            executor=HealthRemoveExerciseExecutor(),
        )]


# --- health_create_competition ---

class HealthCreateCompetitionAction(Action):
    competition: Dict[str, Any] = Field(
        description="Competition dict: name (required), date YYYY-MM-DD (required), federation (required), "
                    "federation_id, counts_toward_federation_ids, status (confirmed/optional/skipped), "
                    "weight_class_kg, location, targets {squat_kg, bench_kg, deadlift_kg, total_kg}, notes"
    )


class HealthCreateCompetitionObservation(Observation):
    pass


class HealthCreateCompetitionExecutor(ToolExecutor[HealthCreateCompetitionAction, HealthCreateCompetitionObservation]):
    def __call__(self, action: HealthCreateCompetitionAction, conversation=None) -> HealthCreateCompetitionObservation:
        from core import health_create_competition
        result = _run_async(health_create_competition(action.competition))
        return HealthCreateCompetitionObservation.from_text(_format_result(result))


class HealthCreateCompetitionTool(ToolDefinition[HealthCreateCompetitionAction, HealthCreateCompetitionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthCreateCompetitionTool"]:
        return [cls(
            description="Create a new competition entry. Required: name, date, federation. Optional: federation_id, counts_toward_federation_ids, status, weight_class_kg, location, targets, notes.",
            action_type=HealthCreateCompetitionAction,
            observation_type=HealthCreateCompetitionObservation,
            executor=HealthCreateCompetitionExecutor(),
        )]


# --- health_delete_competition ---

class HealthDeleteCompetitionAction(Action):
    date: str = Field(description="Competition date to delete (YYYY-MM-DD)")


class HealthDeleteCompetitionObservation(Observation):
    pass


class HealthDeleteCompetitionExecutor(ToolExecutor[HealthDeleteCompetitionAction, HealthDeleteCompetitionObservation]):
    def __call__(self, action: HealthDeleteCompetitionAction, conversation=None) -> HealthDeleteCompetitionObservation:
        from core import health_delete_competition
        result = _run_async(health_delete_competition(action.date))
        return HealthDeleteCompetitionObservation.from_text(_format_result(result))


class HealthDeleteCompetitionTool(ToolDefinition[HealthDeleteCompetitionAction, HealthDeleteCompetitionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthDeleteCompetitionTool"]:
        return [cls(
            description="Delete a competition by date. Cannot be undone.",
            action_type=HealthDeleteCompetitionAction,
            observation_type=HealthDeleteCompetitionObservation,
            executor=HealthDeleteCompetitionExecutor(),
        )]


# --- health_delete_diet_note ---

class HealthDeleteDietNoteAction(Action):
    date: str = Field(description="Diet note date to delete (YYYY-MM-DD)")


class HealthDeleteDietNoteObservation(Observation):
    pass


class HealthDeleteDietNoteExecutor(ToolExecutor[HealthDeleteDietNoteAction, HealthDeleteDietNoteObservation]):
    def __call__(self, action: HealthDeleteDietNoteAction, conversation=None) -> HealthDeleteDietNoteObservation:
        from core import health_delete_diet_note
        result = _run_async(health_delete_diet_note(action.date))
        return HealthDeleteDietNoteObservation.from_text(_format_result(result))


class HealthDeleteDietNoteTool(ToolDefinition[HealthDeleteDietNoteAction, HealthDeleteDietNoteObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthDeleteDietNoteTool"]:
        return [cls(
            description="Delete a diet note by date.",
            action_type=HealthDeleteDietNoteAction,
            observation_type=HealthDeleteDietNoteObservation,
            executor=HealthDeleteDietNoteExecutor(),
        )]


# --- health_update_meta ---

class HealthUpdateMetaAction(Action):
    updates: Dict[str, Any] = Field(
        description="Dict of meta fields to update. Allowed: program_name, comp_date, target_squat_kg, "
                    "target_bench_kg, target_dl_kg, target_total_kg, sex, weight_class_kg, "
                    "current_body_weight_kg, federation, practicing_for, program_start"
    )


class HealthUpdateMetaObservation(Observation):
    pass


class HealthUpdateMetaExecutor(ToolExecutor[HealthUpdateMetaAction, HealthUpdateMetaObservation]):
    def __call__(self, action: HealthUpdateMetaAction, conversation=None) -> HealthUpdateMetaObservation:
        from core import health_update_meta
        result = _run_async(health_update_meta(action.updates))
        return HealthUpdateMetaObservation.from_text(_format_result(result))


class HealthUpdateMetaTool(ToolDefinition[HealthUpdateMetaAction, HealthUpdateMetaObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateMetaTool"]:
        return [cls(
            description=(
                "Update program metadata fields: comp_date, target maxes, sex, body weight, "
                "weight_class_kg, federation, program_start, program_name. Pass only the fields you want to change."
            ),
            action_type=HealthUpdateMetaAction,
            observation_type=HealthUpdateMetaObservation,
            executor=HealthUpdateMetaExecutor(),
        )]


# --- health_update_phases ---

class HealthUpdatePhasesAction(Action):
    phases: List[Dict[str, Any]] = Field(
        description="Complete phases list. Each phase: {name (required), start_week (int), end_week (int), intent (str)}"
    )


class HealthUpdatePhasesObservation(Observation):
    pass


class HealthUpdatePhasesExecutor(ToolExecutor[HealthUpdatePhasesAction, HealthUpdatePhasesObservation]):
    def __call__(self, action: HealthUpdatePhasesAction, conversation=None) -> HealthUpdatePhasesObservation:
        from core import health_update_phases
        result = _run_async(health_update_phases(action.phases))
        return HealthUpdatePhasesObservation.from_text(_format_result(result))


class HealthUpdatePhasesTool(ToolDefinition[HealthUpdatePhasesAction, HealthUpdatePhasesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdatePhasesTool"]:
        return [cls(
            description="Replace the training phases array. Fetch current phases first, modify, then submit the full list.",
            action_type=HealthUpdatePhasesAction,
            observation_type=HealthUpdatePhasesObservation,
            executor=HealthUpdatePhasesExecutor(),
        )]


# --- health_update_current_maxes ---

class HealthUpdateCurrentMaxesAction(Action):
    squat_kg: Optional[float] = Field(default=None, description="New squat max in kg (omit to leave unchanged)")
    bench_kg: Optional[float] = Field(default=None, description="New bench max in kg (omit to leave unchanged)")
    deadlift_kg: Optional[float] = Field(default=None, description="New deadlift max in kg (omit to leave unchanged)")


class HealthUpdateCurrentMaxesObservation(Observation):
    pass


class HealthUpdateCurrentMaxesExecutor(ToolExecutor[HealthUpdateCurrentMaxesAction, HealthUpdateCurrentMaxesObservation]):
    def __call__(self, action: HealthUpdateCurrentMaxesAction, conversation=None) -> HealthUpdateCurrentMaxesObservation:
        from core import health_update_current_maxes
        result = _run_async(health_update_current_maxes(action.squat_kg, action.bench_kg, action.deadlift_kg))
        return HealthUpdateCurrentMaxesObservation.from_text(_format_result(result))


class HealthUpdateCurrentMaxesTool(ToolDefinition[HealthUpdateCurrentMaxesAction, HealthUpdateCurrentMaxesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthUpdateCurrentMaxesTool"]:
        return [cls(
            description="Update current competition maxes (squat_kg, bench_kg, deadlift_kg). Pass only the lifts that changed.",
            action_type=HealthUpdateCurrentMaxesAction,
            observation_type=HealthUpdateCurrentMaxesObservation,
            executor=HealthUpdateCurrentMaxesExecutor(),
        )]


# =============================================================================
# Register all SDK tools
# =============================================================================

register_tool("HealthGetProgramTool", HealthGetProgramTool)
register_tool("HealthSetupStatusTool", HealthSetupStatusTool)
register_tool("HealthSetupInitializeTool", HealthSetupInitializeTool)
register_tool("HealthCompCountdownTool", HealthCompCountdownTool)
register_tool("HealthUpdateSessionTool", HealthUpdateSessionTool)
register_tool("HealthNewVersionTool", HealthNewVersionTool)
register_tool("KgToLbTool", KgToLbTool)
register_tool("LbToKgTool", LbToKgTool)
register_tool("IpfWeightClassesTool", IpfWeightClassesTool)
register_tool("PctOfMaxTool", PctOfMaxTool)
register_tool("CalculateAttemptsTool", CalculateAttemptsTool)
register_tool("HealthRagSearchTool", HealthRagSearchTool)
register_tool("HealthGetCompetitionTool", HealthGetCompetitionTool)
register_tool("HealthListCompetitionsTool", HealthListCompetitionsTool)
register_tool("HealthGetDietNotesTool", HealthGetDietNotesTool)
register_tool("HealthGetSessionTool", HealthGetSessionTool)
register_tool("HealthGetSessionsRangeTool", HealthGetSessionsRangeTool)
register_tool("HealthGetSupplementsTool", HealthGetSupplementsTool)
register_tool("HealthGetMetaTool", HealthGetMetaTool)
register_tool("HealthGetPhasesTool", HealthGetPhasesTool)
register_tool("HealthGetCurrentMaxesTool", HealthGetCurrentMaxesTool)
register_tool("HealthGetGoalsTool", HealthGetGoalsTool)
register_tool("HealthUpdateGoalsTool", HealthUpdateGoalsTool)
register_tool("HealthGetFederationLibraryTool", HealthGetFederationLibraryTool)
register_tool("HealthUpdateFederationLibraryTool", HealthUpdateFederationLibraryTool)
register_tool("HealthGetOperatorPrefsTool", HealthGetOperatorPrefsTool)
register_tool("HealthGetBreaksTool", HealthGetBreaksTool)
register_tool("DaysUntilTool", DaysUntilTool)
register_tool("HealthUpdateCompetitionTool", HealthUpdateCompetitionTool)
register_tool("HealthSnapshotCompetitionProjectionTool", HealthSnapshotCompetitionProjectionTool)
register_tool("HealthCompleteCompetitionTool", HealthCompleteCompetitionTool)
register_tool("HealthUpdateDietNoteTool", HealthUpdateDietNoteTool)
register_tool("HealthUpdateSupplementsTool", HealthUpdateSupplementsTool)
register_tool("HealthCreateSessionTool", HealthCreateSessionTool)
register_tool("HealthDeleteSessionTool", HealthDeleteSessionTool)
register_tool("HealthRescheduleSessionTool", HealthRescheduleSessionTool)
register_tool("HealthAddExerciseTool", HealthAddExerciseTool)
register_tool("HealthRemoveExerciseTool", HealthRemoveExerciseTool)
register_tool("HealthCreateCompetitionTool", HealthCreateCompetitionTool)
register_tool("HealthDeleteCompetitionTool", HealthDeleteCompetitionTool)
register_tool("HealthDeleteDietNoteTool", HealthDeleteDietNoteTool)
register_tool("HealthUpdateMetaTool", HealthUpdateMetaTool)
register_tool("HealthUpdatePhasesTool", HealthUpdatePhasesTool)
register_tool("HealthUpdateCurrentMaxesTool", HealthUpdateCurrentMaxesTool)


# =============================================================================
# Analytics & Export Tools
# =============================================================================

# --- export_program_history ---

def _build_analysis_bundle(program: dict, sessions: list[dict]) -> dict:
    """Assemble the analysis bundle threaded into the XLSX export.

    Uses cached AI reports (no forced regeneration) and the pure weekly_analysis
    function. Missing pieces degrade gracefully — each piece is independently
    wrapped so one failure doesn't cascade.
    """
    import logging

    from config import IF_HEALTH_TABLE_NAME
    from core import _get_store
    from prompt_context import summarize_lift_profiles

    logger = logging.getLogger(__name__)
    store = _get_store()
    active_pk = store.pk
    cache_version = getattr(store, "_cache_version", None)
    version_token = f"v{int(cache_version):03d}" if isinstance(cache_version, int) and cache_version > 0 else ""

    bundle: dict[str, Any] = {
        "weekly": None,
        "correlation": None,
        "program_evaluation": None,
        "lift_profiles": summarize_lift_profiles(program.get("lift_profiles")),
        "pk": active_pk,
        "version": version_token,
        "sex": str((program.get("meta") or {}).get("sex") or "male").lower(),
    }

    try:
        glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
    except Exception as e:
        logger.warning("export: glossary fetch failed (%s); continuing without it", e)
        glossary = []

    bundle["glossary"] = glossary

    try:
        bundle["federation_library"] = _get_versioned_item_sync(IF_HEALTH_TABLE_NAME, active_pk, "federations#v1") or {
            "pk": active_pk,
            "sk": "federations#v1",
            "updated_at": "",
            "federations": [],
            "qualification_standards": [],
        }
    except Exception as e:
        logger.warning("export: federation library fetch failed (%s); continuing without it", e)
        bundle["federation_library"] = {
            "pk": active_pk,
            "sk": "federations#v1",
            "updated_at": "",
            "federations": [],
            "qualification_standards": [],
        }

    try:
        if version_token:
            weight_log_item = _get_versioned_item_sync(IF_HEALTH_TABLE_NAME, active_pk, f"weight_log#{version_token}")
            bundle["weight_log"] = (weight_log_item or {}).get("entries", [])
        else:
            bundle["weight_log"] = []
    except Exception as e:
        logger.warning("export: weight log fetch failed (%s); continuing without it", e)
        bundle["weight_log"] = []

    try:
        if version_token:
            max_history_item = _get_versioned_item_sync(IF_HEALTH_TABLE_NAME, active_pk, f"max_history#{version_token}")
            bundle["max_history"] = (max_history_item or {}).get("entries", [])
        else:
            bundle["max_history"] = []
    except Exception as e:
        logger.warning("export: max history fetch failed (%s); continuing without it", e)
        bundle["max_history"] = []

    try:
        from datetime import datetime
        block_sessions = [s for s in sessions if s.get("block", "current") == "current" and s.get("date")]
        if not block_sessions:
            effective_weeks = 4
        else:
            block_sessions.sort(key=lambda x: x["date"])
            first = datetime.fromisoformat(block_sessions[0]["date"][:10])
            last = datetime.fromisoformat(block_sessions[-1]["date"][:10])
            diff_days = abs((last - first).days)
            # Frontend uses Math.ceil(diff / 7), so days//7 + 1 or similar
            # Since frontend does: diffTime / (7 days), then Math.ceil
            # Let's match frontend more closely:
            effective_weeks = max(int((diff_days / 7) + 0.999), 4)
    except Exception as e:
        logger.warning("export: effective_weeks calculation failed: %s", e)
        effective_weeks = 4

    try:
        from datetime import datetime
        current_sessions = [s for s in sessions if (s.get("block") or "current") == "current"]
        current_week = max(
            (int(s.get("week_number", 0)) for s in current_sessions if s.get("week_number")),
            default=effective_weeks,
        )
        bundle["weekly"] = _build_sectioned_week_analysis(
            program,
            current_sessions,
            glossary,
            week_start=max(1, current_week - effective_weeks + 1),
            week_end=current_week,
            ref_date=datetime.utcnow().date().isoformat(),
        )
    except Exception as e:
        logger.warning("export: weekly_analysis failed: %s", e)

    try:
        bundle["correlation"] = _read_cached_correlation(weeks=effective_weeks)
    except Exception as e:
        logger.warning("export: correlation cache read failed: %s", e)

    try:
        from core import health_program_evaluation
        bundle["program_evaluation"] = _run_async(health_program_evaluation(refresh=False, cache_only=True))
    except Exception as e:
        logger.warning("export: program_evaluation read failed: %s", e)

    return bundle


def _read_cached_correlation(weeks: int = 4) -> dict | None:
    """Return the cached correlation report for the current window, or None."""
    from datetime import datetime, timedelta

    import boto3

    from config import IF_HEALTH_TABLE_NAME
    from core import _get_store

    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    window_start = (raw_cutoff - timedelta(days=raw_cutoff.weekday())).isoformat()
    cache_sk = f"corr_report#{window_start}_{weeks}w"

    table = boto3.resource("dynamodb", region_name="ca-central-1").Table(IF_HEALTH_TABLE_NAME)
    item = table.get_item(Key={"pk": _get_store().pk, "sk": cache_sk}).get("Item")
    if not item or not item.get("report"):
        return None

    report = item["report"]
    if isinstance(report, dict):
        report["cached"] = True
        report["generated_at"] = item.get("generated_at", "")
        report["window_start"] = window_start
        report["weeks"] = weeks
    return _sanitize_decimals(report)


def _scope_program_to_current_block(program: dict) -> dict:
    """Return a shallow copy of program with phases and sessions filtered to the current block only."""
    scoped = dict(program)
    scoped["phases"] = [p for p in program.get("phases", []) if (p.get("block") or "current") == "current"]
    scoped["sessions"] = [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]
    return scoped


def _normalize_export_format(format_value: str | None) -> str:
    export_format = str(format_value or "xlsx").strip().lower()
    if export_format in ("md", "markdown"):
        return "markdown"
    if export_format == "xlsx":
        return "xlsx"
    raise ValueError(f"Unsupported export format: {format_value!r}. Use 'xlsx' or 'markdown'.")


def _write_program_export(program: dict, sessions: list[dict], out_dir: str, format_value: str | None) -> tuple[str, str, str]:
    import os
    from export import build_program_markdown, build_program_xlsx

    export_format = _normalize_export_format(format_value)
    scoped_program = _scope_program_to_current_block(program)
    scoped_sessions = scoped_program["sessions"]
    analysis = _build_analysis_bundle(program, sessions)

    if export_format == "markdown":
        filename = "program_history.md"
        description = "Markdown export of current block"
        out_path = os.path.join(out_dir, filename)
        build_program_markdown(scoped_program, out_path, analysis=analysis, export_context=analysis)
        return filename, description, export_format

    filename = "program_history.xlsx"
    description = "Excel export of current block"
    out_path = os.path.join(out_dir, filename)
    build_program_xlsx(scoped_program, out_path, analysis=analysis, export_context=analysis)
    return filename, description, export_format


class ExportProgramHistoryAction(Action):
    format: str = Field(default="xlsx", description="Export format: 'xlsx' or 'markdown'")


class ExportProgramHistoryObservation(Observation):
    pass


class ExportProgramHistoryExecutor(ToolExecutor[ExportProgramHistoryAction, ExportProgramHistoryObservation]):
    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    def __call__(self, action: ExportProgramHistoryAction, conversation=None) -> ExportProgramHistoryObservation:
        import os
        import tempfile
        from core import _get_store

        program = _run_async(_get_store().get_program())
        sessions = program.get("sessions", []) if isinstance(program, dict) else []

        if self.chat_id:
            try:
                from app_sandbox import get_local_sandbox
                work_dir = get_local_sandbox().get_working_dir(self.chat_id)
            except Exception:
                work_dir = tempfile.gettempdir()
        else:
            work_dir = tempfile.gettempdir()

        os.makedirs(work_dir, exist_ok=True)
        filename, description, _ = _write_program_export(program, sessions, work_dir, action.format)

        return ExportProgramHistoryObservation.from_text(
            f"Exported program history to {filename}.\n"
            f"Emit this line at the end of your reply:\n"
            f"FILES: {filename} ({description})"
        )


class ExportProgramHistoryTool(ToolDefinition[ExportProgramHistoryAction, ExportProgramHistoryObservation]):
    @classmethod
    def create(cls, conv_state=None, chat_id: str = "", **params) -> Sequence["ExportProgramHistoryTool"]:
        return [cls(
            description=(
                "Export the full training program to an Excel (.xlsx) or Markdown (.md) file. "
                "Sheets: Meta, Current Maxes, Phases, Sessions, Exercises, Competitions, "
                "Lift Profiles, Weekly Analysis, Per-Lift Metrics, ROI Correlation, Program Evaluation. "
                "Weekly Analysis is deterministic; ROI Correlation and Program Evaluation use cached AI values only. "
                "Refresh AI sections from their own Analysis page buttons first if you want the freshest data. "
                "After calling this tool, emit a FILES: line to deliver the file."
            ),
            action_type=ExportProgramHistoryAction,
            observation_type=ExportProgramHistoryObservation,
            executor=ExportProgramHistoryExecutor(chat_id=chat_id),
        )]


# --- analyze_progression ---

class AnalyzeProgressionAction(Action):
    exercise_name: str = Field(description="Name of the exercise (e.g. 'Squat', 'Bench Press')")
    weeks: Optional[int] = Field(default=None, description="Number of recent weeks to analyze (default: all available)")


class AnalyzeProgressionObservation(Observation):
    pass


class AnalyzeProgressionExecutor(ToolExecutor[AnalyzeProgressionAction, AnalyzeProgressionObservation]):
    def __call__(self, action: AnalyzeProgressionAction, conversation=None) -> AnalyzeProgressionObservation:
        from datetime import timedelta
        from core import _get_store
        from analytics import progression_rate, _calculate_current_week, _parse_date

        program = _run_async(_get_store().get_program())
        sessions = program.get("sessions", [])
        program_start = program.get("meta", {}).get("program_start", "")

        if action.weeks > 0:
            cutoff_week = _calculate_current_week(program_start, sessions) - action.weeks
            start = _parse_date(program_start)
            if start:
                cutoff_date = start + timedelta(weeks=cutoff_week)
                sessions = [s for s in sessions if _parse_date(s.get("date", "")) and _parse_date(s.get("date", "")) >= cutoff_date]

        result = progression_rate(sessions, action.exercise_name, program_start)
        return AnalyzeProgressionObservation.from_text(_format_result(result))


class AnalyzeProgressionTool(ToolDefinition[AnalyzeProgressionAction, AnalyzeProgressionObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["AnalyzeProgressionTool"]:
        return [cls(
            description=(
                "Calculate the weekly progression rate (kg/week) for a specific lift using Theil-Sen regression "
                "on top sets across completed sessions. Returns slope, Kendall tau, fit quality, and data points."
            ),
            action_type=AnalyzeProgressionAction,
            observation_type=AnalyzeProgressionObservation,
            executor=AnalyzeProgressionExecutor(),
        )]


# --- analyze_rpe_drift ---

class AnalyzeRpeDriftAction(Action):
    exercise_name: str = Field(description="Name of the exercise")
    window_weeks: int = Field(default=4, description="Number of weeks to analyze for drift")


class AnalyzeRpeDriftObservation(Observation):
    pass


class AnalyzeRpeDriftExecutor(ToolExecutor[AnalyzeRpeDriftAction, AnalyzeRpeDriftObservation]):
    def __call__(self, action: AnalyzeRpeDriftAction, conversation=None) -> AnalyzeRpeDriftObservation:
        from core import _get_store
        from analytics import rpe_drift

        program = _run_async(_get_store().get_program())
        sessions = program.get("sessions", [])
        program_start = program.get("meta", {}).get("program_start", "")

        result = rpe_drift(sessions, action.exercise_name, program_start, action.window_weeks)
        return AnalyzeRpeDriftObservation.from_text(_format_result(result))


class AnalyzeRpeDriftTool(ToolDefinition[AnalyzeRpeDriftAction, AnalyzeRpeDriftObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["AnalyzeRpeDriftTool"]:
        return [cls(
            description=(
                "Detect RPE drift for a lift — whether perceived exertion is trending up at the same loads "
                "(fatigue signal) or down (adaptation). Flags 'fatigue' if RPE is rising >= 0.1/week."
            ),
            action_type=AnalyzeRpeDriftAction,
            observation_type=AnalyzeRpeDriftObservation,
            executor=AnalyzeRpeDriftExecutor(),
        )]


# --- estimate_1rm ---

class Estimate1rmAction(Action):
    weight_kg: float = Field(description="Weight lifted in kg")
    reps: int = Field(description="Number of repetitions performed")
    rpe: Optional[int] = Field(default=None, description="RPE of the set (6-10), enables RPE-based estimation")


class Estimate1rmObservation(Observation):
    pass


class Estimate1rmExecutor(ToolExecutor[Estimate1rmAction, Estimate1rmObservation]):
    def __call__(self, action: Estimate1rmAction, conversation=None) -> Estimate1rmObservation:
        from analytics import estimate_1rm
        result = estimate_1rm(action.weight_kg, action.reps, action.rpe)
        return Estimate1rmObservation.from_text(_format_result(result))


class Estimate1rmTool(ToolDefinition[Estimate1rmAction, Estimate1rmObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["Estimate1rmTool"]:
        return [cls(
            description=(
                "Estimate one-rep max from a working set using Epley, Brzycki, and RPE-based formulas. "
                "Provide weight, reps, and optionally RPE for the most accurate RPE-table estimate."
            ),
            action_type=Estimate1rmAction,
            observation_type=Estimate1rmObservation,
            executor=Estimate1rmExecutor(),
        )]


# --- calculate_dots ---

class CalculateDotsAction(Action):
    total_kg: float = Field(description="Combined squat + bench + deadlift total in kg")
    bodyweight_kg: float = Field(description="Lifter bodyweight in kg")
    sex: str = Field(description="'male' or 'female'")


class CalculateDotsObservation(Observation):
    pass


class CalculateDotsExecutor(ToolExecutor[CalculateDotsAction, CalculateDotsObservation]):
    def __call__(self, action: CalculateDotsAction, conversation=None) -> CalculateDotsObservation:
        from analytics import calculate_dots
        result = calculate_dots(action.total_kg, action.bodyweight_kg, action.sex)
        return CalculateDotsObservation.from_text(_format_result({"dots": result}))


class CalculateDotsTool(ToolDefinition[CalculateDotsAction, CalculateDotsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["CalculateDotsTool"]:
        return [cls(
            description=(
                "Calculate DOTS (Dynamic Objective Total Score) from a competition total and bodyweight. "
                "Used for comparing strength across weight classes and sexes."
            ),
            action_type=CalculateDotsAction,
            observation_type=CalculateDotsObservation,
            executor=CalculateDotsExecutor(),
        )]


# --- weekly_analysis ---

class WeeklyAnalysisAction(Action):
    weeks: int = Field(default=1, description="Number of weeks to analyze (default: 1)")
    block: str = Field(default="current", description="Program block filter (default 'current')")
    week_start: int | None = Field(default=None, description="Inclusive training week number to start analysis")
    week_end: int | None = Field(default=None, description="Inclusive training week number to end analysis")
    window_start: str | None = Field(default=None, description="Optional date window start (YYYY-MM-DD) for time-series context")
    window_end: str | None = Field(default=None, description="Optional date window end (YYYY-MM-DD) for time-series context")
    ref_date: str | None = Field(default=None, description="Optional reference date (YYYY-MM-DD)")
    refresh_program: bool = Field(default=True, description="Invalidate the program cache before analysis")
    program: Optional[Dict[str, Any]] = Field(default=None, description="Optional program snapshot supplied by the caller")
    sessions: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional session snapshot supplied by the caller")


class WeeklyAnalysisObservation(Observation):
    pass


class WeeklyAnalysisExecutor(ToolExecutor[WeeklyAnalysisAction, WeeklyAnalysisObservation]):
    def __call__(self, action: WeeklyAnalysisAction, conversation=None) -> WeeklyAnalysisObservation:
        from core import _get_store
        from config import IF_HEALTH_TABLE_NAME

        store = _get_store()
        if action.refresh_program:
            store.invalidate_cache()
        if isinstance(action.program, dict):
            program = dict(action.program)
            sessions = action.sessions if isinstance(action.sessions, list) else program.get("sessions", [])
            program["sessions"] = sessions if isinstance(sessions, list) else []
        else:
            program = _run_async(store.get_program())
            sessions = program.get("sessions", [])
        glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
        result = _build_sectioned_analysis(
            program,
            sessions,
            glossary,
            weeks=action.weeks,
            block=action.block,
            window_start=action.window_start,
            window_end=action.window_end,
            ref_date=action.ref_date,
            week_start=action.week_start,
            week_end=action.week_end,
        )
        return WeeklyAnalysisObservation.from_text(_format_result(result))


class WeeklyAnalysisTool(ToolDefinition[WeeklyAnalysisAction, WeeklyAnalysisObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["WeeklyAnalysisTool"]:
        return [cls(
            description=(
                "Full weekly training analysis — runs progression rate, RPE drift, fatigue index, "
                "periodization compliance, peaking metrics, and meet projection for the specified "
                "number of weeks. Returns structured JSON with per-lift breakdowns, flags, and "
                "projected total."
            ),
            action_type=WeeklyAnalysisAction,
            observation_type=WeeklyAnalysisObservation,
            executor=WeeklyAnalysisExecutor(),
        )]


register_tool("ExportProgramHistoryTool", ExportProgramHistoryTool)
register_tool("AnalyzeProgressionTool", AnalyzeProgressionTool)
register_tool("AnalyzeRpeDriftTool", AnalyzeRpeDriftTool)
register_tool("Estimate1rmTool", Estimate1rmTool)
register_tool("CalculateDotsTool", CalculateDotsTool)
register_tool("WeeklyAnalysisTool", WeeklyAnalysisTool)


# --- correlation_analysis ---

class CorrelationAnalysisAction(Action):
    weeks: int = Field(default=4, description="Rolling window in weeks (default 4)")
    block: str = Field(default="current", description="Program block filter (default 'current')")
    refresh: bool = Field(default=False, description="Force regeneration, ignore cache")
    cache_only: bool = Field(default=False, description="Return only cached results; do not generate a new AI report")


class CorrelationAnalysisObservation(Observation):
    pass


class CorrelationAnalysisExecutor(ToolExecutor[CorrelationAnalysisAction, CorrelationAnalysisObservation]):
    def __call__(self, action: CorrelationAnalysisAction, conversation=None) -> CorrelationAnalysisObservation:
        from datetime import datetime, timedelta
        import time

        from core import _get_store, _floats_to_decimals
        from correlation_ai import generate_correlation_report
        from config import IF_HEALTH_TABLE_NAME, AWS_REGION
        import boto3

        today = datetime.utcnow().date()
        raw_cutoff = today - timedelta(weeks=action.weeks)
        days_since_monday = raw_cutoff.weekday()
        window_start = raw_cutoff - timedelta(days=days_since_monday)
        window_start_str = window_start.isoformat()
        cache_sk = f"corr_report#{window_start_str}_{action.weeks}w"

        store = _get_store()
        active_pk = store.pk
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(IF_HEALTH_TABLE_NAME)

        if not action.refresh:
            cached = table.get_item(Key={"pk": active_pk, "sk": cache_sk}).get("Item")
            if cached and cached.get("report"):
                report = cached["report"]
                if isinstance(report, dict):
                    report["cached"] = True
                    report["generated_at"] = cached.get("generated_at", "")
                    report["window_start"] = window_start_str
                    report["weeks"] = action.weeks
                return CorrelationAnalysisObservation.from_text(_format_result(report))

        if action.cache_only:
            return CorrelationAnalysisObservation.from_text(_format_result({
                "findings": [],
                "summary": "",
                "insufficient_data": True,
                "insufficient_data_reason": "No cached ROI correlation report exists. Generate it to run AI analysis.",
                "cache_miss": True,
                "cached": False,
                "generated_at": "",
                "window_start": window_start_str,
                "weeks": action.weeks,
            }))

        store.invalidate_cache()
        program = _run_async(store.get_program())
        sessions = program.get("sessions", [])
        lift_profiles = program.get("lift_profiles", [])

        report = _run_async(generate_correlation_report(
            sessions=sessions,
            lift_profiles=lift_profiles,
            weeks=action.weeks,
            window_start=window_start_str,
            program=program,
        ))

        generated_at = datetime.utcnow().isoformat() + "Z"

        table.put_item(Item=_floats_to_decimals({
            "pk": active_pk,
            "sk": cache_sk,
            "report": report,
            "generated_at": generated_at,
            "window_start": window_start_str,
            "weeks": action.weeks,
            # 7-day TTL — not invalidated by session changes
            "expires_at": int(time.time()) + 7 * 86400,
        }))

        report["cached"] = False
        report["generated_at"] = generated_at
        report["window_start"] = window_start_str
        report["weeks"] = action.weeks
        return CorrelationAnalysisObservation.from_text(_format_result(report))


class CorrelationAnalysisTool(ToolDefinition[CorrelationAnalysisAction, CorrelationAnalysisObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["CorrelationAnalysisTool"]:
        return [cls(
            description=(
                "AI-powered exercise ROI correlation analysis. Identifies which accessory "
                "exercises correlate with improvements in squat/bench/deadlift over a rolling "
                "window. Results are cached in DynamoDB. Use refresh=true to force regeneration."
            ),
            action_type=CorrelationAnalysisAction,
            observation_type=CorrelationAnalysisObservation,
            executor=CorrelationAnalysisExecutor(),
        )]


# --- fatigue_profile_estimate ---

class FatigueProfileEstimateAction(Action):
    exercise: dict = Field(
        description="Exercise metadata: name, category, equipment, muscles, description, how_to_perform, why_do_it"
    )


class FatigueProfileEstimateObservation(Observation):
    pass


class FatigueProfileEstimateExecutor(ToolExecutor[FatigueProfileEstimateAction, FatigueProfileEstimateObservation]):
    def __call__(self, action: FatigueProfileEstimateAction, conversation=None) -> FatigueProfileEstimateObservation:
        from fatigue_ai import estimate_fatigue_profile
        program_meta, lift_profiles = _fatigue_context()
        result = _run_async(estimate_fatigue_profile(
            action.exercise,
            program_meta=program_meta,
            lift_profiles=lift_profiles,
        ))
        return FatigueProfileEstimateObservation.from_text(_format_result(result))


class FatigueProfileEstimateTool(ToolDefinition[FatigueProfileEstimateAction, FatigueProfileEstimateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FatigueProfileEstimateTool"]:
        return [cls(
            description=(
                "Estimate the fatigue profile (axial/neural/peripheral/systemic components) for "
                "an exercise using AI analysis of its biomechanical characteristics."
            ),
            action_type=FatigueProfileEstimateAction,
            observation_type=FatigueProfileEstimateObservation,
            executor=FatigueProfileEstimateExecutor(),
        )]


class MuscleGroupEstimateAction(Action):
    exercise: dict = Field(
        description="Exercise metadata: name, category, equipment, description, how_to_perform, why_do_it, and any existing muscle annotations"
    )
    lift_profiles: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional squat/bench/deadlift lift profiles to use as immediate context for the estimate",
    )


class MuscleGroupEstimateObservation(Observation):
    pass


class MuscleGroupEstimateExecutor(ToolExecutor[MuscleGroupEstimateAction, MuscleGroupEstimateObservation]):
    def __call__(self, action: MuscleGroupEstimateAction, conversation=None) -> MuscleGroupEstimateObservation:
        result = _do_muscle_group_estimate({
            "exercise": action.exercise,
            "lift_profiles": action.lift_profiles,
        })
        return MuscleGroupEstimateObservation.from_text(_format_result(result))


class MuscleGroupEstimateTool(ToolDefinition[MuscleGroupEstimateAction, MuscleGroupEstimateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["MuscleGroupEstimateTool"]:
        return [cls(
            description=(
                "Estimate the primary, secondary, and tertiary muscle groups for an exercise "
                "using AI analysis of movement pattern and athlete lift profile context."
            ),
            action_type=MuscleGroupEstimateAction,
            observation_type=MuscleGroupEstimateObservation,
            executor=MuscleGroupEstimateExecutor(),
        )]


class GlossaryGenerateTextAction(Action):
    exercise: dict = Field(
        description="Exercise metadata: name, category, equipment, primary_muscles, secondary_muscles, tertiary_muscles"
    )
    lift_profiles: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional squat/bench/deadlift lift profiles to use as brief context",
    )


class GlossaryGenerateTextObservation(Observation):
    pass


class GlossaryGenerateTextExecutor(ToolExecutor[GlossaryGenerateTextAction, GlossaryGenerateTextObservation]):
    def __call__(self, action: GlossaryGenerateTextAction, conversation=None) -> GlossaryGenerateTextObservation:
        result = _do_glossary_generate_text({
            "exercise": action.exercise,
            "lift_profiles": action.lift_profiles,
        })
        return GlossaryGenerateTextObservation.from_text(_format_result(result))


class GlossaryGenerateTextTool(ToolDefinition[GlossaryGenerateTextAction, GlossaryGenerateTextObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryGenerateTextTool"]:
        return [cls(
            description=(
                "Generate concise glossary text fields for an exercise: what it is, "
                "how to perform it, and why to use it."
            ),
            action_type=GlossaryGenerateTextAction,
            observation_type=GlossaryGenerateTextObservation,
            executor=GlossaryGenerateTextExecutor(),
        )]


class LiftProfileReviewAction(Action):
    profile: dict = Field(description="Lift profile dict with lift, style_notes, sticking_points, primary_muscle, and volume_tolerance")


class LiftProfileReviewObservation(Observation):
    pass


class LiftProfileReviewExecutor(ToolExecutor[LiftProfileReviewAction, LiftProfileReviewObservation]):
    def __call__(self, action: LiftProfileReviewAction, conversation=None) -> LiftProfileReviewObservation:
        from lift_profile_ai import review_lift_profile
        result = _run_async(review_lift_profile(action.profile))
        return LiftProfileReviewObservation.from_text(_format_result(result))


class LiftProfileReviewTool(ToolDefinition[LiftProfileReviewAction, LiftProfileReviewObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["LiftProfileReviewTool"]:
        return [cls(
            description=(
                "Review a squat/bench/deadlift style profile for missing biomechanical details "
                "needed to estimate a lift-specific INOL stimulus coefficient."
            ),
            action_type=LiftProfileReviewAction,
            observation_type=LiftProfileReviewObservation,
            executor=LiftProfileReviewExecutor(),
        )]


class LiftProfileRewriteEstimateAction(Action):
    profile: dict = Field(description="Lift profile dict to clean up and estimate a 1-2 INOL stimulus coefficient for")


class LiftProfileRewriteEstimateObservation(Observation):
    pass


class LiftProfileRewriteEstimateExecutor(ToolExecutor[LiftProfileRewriteEstimateAction, LiftProfileRewriteEstimateObservation]):
    def __call__(self, action: LiftProfileRewriteEstimateAction, conversation=None) -> LiftProfileRewriteEstimateObservation:
        from lift_profile_ai import rewrite_and_estimate_lift_profile
        result = _run_async(rewrite_and_estimate_lift_profile(action.profile))
        return LiftProfileRewriteEstimateObservation.from_text(_format_result(result))


class LiftProfileRewriteEstimateTool(ToolDefinition[LiftProfileRewriteEstimateAction, LiftProfileRewriteEstimateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["LiftProfileRewriteEstimateTool"]:
        return [cls(
            description=(
                "Rewrite a lift style profile for analysis clarity and estimate its 1-2 "
                "INOL stimulus coefficient against a baseline of 1.0."
            ),
            action_type=LiftProfileRewriteEstimateAction,
            observation_type=LiftProfileRewriteEstimateObservation,
            executor=LiftProfileRewriteEstimateExecutor(),
        )]


register_tool("CorrelationAnalysisTool", CorrelationAnalysisTool)
register_tool("FatigueProfileEstimateTool", FatigueProfileEstimateTool)
register_tool("MuscleGroupEstimateTool", MuscleGroupEstimateTool)
register_tool("GlossaryGenerateTextTool", GlossaryGenerateTextTool)
register_tool("LiftProfileReviewTool", LiftProfileReviewTool)
register_tool("LiftProfileRewriteEstimateTool", LiftProfileRewriteEstimateTool)


# --- program_evaluation ---

class ProgramEvaluationAction(Action):
    refresh: bool = Field(default=False, description="Force regeneration, ignore cache")
    cache_only: bool = Field(default=False, description="Return only cached results; do not generate a new AI report")


class ProgramEvaluationObservation(Observation):
    pass


class ProgramEvaluationExecutor(ToolExecutor[ProgramEvaluationAction, ProgramEvaluationObservation]):
    def __call__(self, action: ProgramEvaluationAction, conversation=None) -> ProgramEvaluationObservation:
        from core import health_program_evaluation
        result = _run_async(health_program_evaluation(refresh=action.refresh, cache_only=action.cache_only))
        return ProgramEvaluationObservation.from_text(_format_result(result))


class ProgramEvaluationTool(ToolDefinition[ProgramEvaluationAction, ProgramEvaluationObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ProgramEvaluationTool"]:
        return [cls(
            description=(
                "Full-block program evaluation by an AI sports scientist. "
                "Evaluates the current training block against competition goals, identifies what is working, "
                "what is not, and suggests small targeted changes. "
                "Only available for the full block (requires >= 4 completed weeks). "
                "Results are cached weekly in DynamoDB. Use refresh=true to force regeneration."
            ),
            action_type=ProgramEvaluationAction,
            observation_type=ProgramEvaluationObservation,
            executor=ProgramEvaluationExecutor(),
        )]


register_tool("ProgramEvaluationTool", ProgramEvaluationTool)


# --- powerlifting_filter_categories ---

class PowerliftingFilterCategoriesAction(Action):
    pass


class PowerliftingFilterCategoriesObservation(Observation):
    pass


class PowerliftingFilterCategoriesExecutor(ToolExecutor[PowerliftingFilterCategoriesAction, PowerliftingFilterCategoriesObservation]):
    def __call__(self, action: PowerliftingFilterCategoriesAction, conversation=None) -> PowerliftingFilterCategoriesObservation:
        from powerlifting_stats import load_data, get_filter_categories, DatasetNotReadyError
        try:
            df = load_data()
            categories = get_filter_categories(df)
            return PowerliftingFilterCategoriesObservation.from_text(_format_result(categories))
        except DatasetNotReadyError as e:
            return PowerliftingFilterCategoriesObservation.from_text(f"ERROR: Dataset not ready. {e}")
        except FileNotFoundError as e:
            return PowerliftingFilterCategoriesObservation.from_text(f"ERROR: Dataset missing. {e}")


class PowerliftingFilterCategoriesTool(ToolDefinition[PowerliftingFilterCategoriesAction, PowerliftingFilterCategoriesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["PowerliftingFilterCategoriesTool"]:
        return [cls(
            description=(
                "Retrieves the unique options (categories) available for filtering "
                "the OpenPowerlifting dataset (e.g. federations, countries, equipment, etc)."
            ),
            action_type=PowerliftingFilterCategoriesAction,
            observation_type=PowerliftingFilterCategoriesObservation,
            executor=PowerliftingFilterCategoriesExecutor(),
        )]

register_tool("PowerliftingFilterCategoriesTool", PowerliftingFilterCategoriesTool)


# --- analyze_powerlifting_stats ---

class AnalyzePowerliftingStatsAction(Action):
    squat_kg: Optional[float] = Field(default=None, description="User's best squat in kg")
    bench_kg: Optional[float] = Field(default=None, description="User's best bench in kg")
    deadlift_kg: Optional[float] = Field(default=None, description="User's best deadlift in kg")
    bodyweight_kg: Optional[float] = Field(default=None, description="User's bodyweight in kg (used to compute DOTS)")
    sex_code: Optional[str] = Field(default=None, description="User's sex for DOTS calculation: 'M' or 'F'")

    federation: Optional[str] = Field(default=None, description="Filter by federation")
    country: Optional[str] = Field(default=None, description="Filter by country")
    region: Optional[str] = Field(default=None, description="Filter by region/state")
    equipment: Optional[str] = Field(default=None, description="Filter by equipment (e.g. Raw)")
    sex: Optional[str] = Field(default=None, description="Filter by sex (e.g. M or F)")
    age_class: Optional[str] = Field(default=None, description="Filter by age class")
    year: Optional[int] = Field(default=None, description="Filter by year of competition")
    event_type: Optional[str] = Field(default=None, description="Filter by event type (e.g. SBD)")
    min_dots: Optional[float] = Field(default=None, description="Minimum DOTS score")


class AnalyzePowerliftingStatsObservation(Observation):
    pass


class AnalyzePowerliftingStatsExecutor(ToolExecutor[AnalyzePowerliftingStatsAction, AnalyzePowerliftingStatsObservation]):
    def __call__(self, action: AnalyzePowerliftingStatsAction, conversation=None) -> AnalyzePowerliftingStatsObservation:
        from powerlifting_stats import load_data, filter_dataset, analyze_stats, DatasetNotReadyError
        try:
            df = load_data()
        except DatasetNotReadyError as e:
            return AnalyzePowerliftingStatsObservation.from_text(f"ERROR: Dataset not ready. {e}")
        except FileNotFoundError as e:
            return AnalyzePowerliftingStatsObservation.from_text(f"ERROR: Dataset missing. {e}")
        filtered_df = filter_dataset(
            df,
            federation=action.federation,
            country=action.country,
            region=action.region,
            equipment=action.equipment,
            sex=action.sex,
            age_class=action.age_class,
            year=action.year,
            event_type=action.event_type,
            min_dots=action.min_dots,
        )
        stats = analyze_stats(
            filtered_df,
            squat_kg=action.squat_kg,
            bench_kg=action.bench_kg,
            deadlift_kg=action.deadlift_kg,
            bodyweight_kg=action.bodyweight_kg,
            sex_code=action.sex_code,
        )
        return AnalyzePowerliftingStatsObservation.from_text(_format_result(stats))


class AnalyzePowerliftingStatsTool(ToolDefinition[AnalyzePowerliftingStatsAction, AnalyzePowerliftingStatsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["AnalyzePowerliftingStatsTool"]:
        return [cls(
            description=(
                "Compares a user's powerlifting stats (SBD, Total, DOTS) against the "
                "OpenPowerlifting dataset using various filters (age, sex, federation, etc) "
                "and returns percentile rankings and dataset statistics."
            ),
            action_type=AnalyzePowerliftingStatsAction,
            observation_type=AnalyzePowerliftingStatsObservation,
            executor=AnalyzePowerliftingStatsExecutor(),
        )]

register_tool("AnalyzePowerliftingStatsTool", AnalyzePowerliftingStatsTool)


# =============================================================================
# Plugin contract: get_tools()
# =============================================================================

def get_tools() -> List[Tool]:
    """Get all health SDK Tool objects (side effect: register_tool already called above)."""
    return [
        Tool(name="HealthGetProgramTool"),
        Tool(name="HealthSetupStatusTool"),
        Tool(name="HealthSetupInitializeTool"),
        Tool(name="HealthCompCountdownTool"),
        Tool(name="HealthUpdateSessionTool"),
        Tool(name="HealthNewVersionTool"),
        Tool(name="KgToLbTool"),
        Tool(name="LbToKgTool"),
        Tool(name="IpfWeightClassesTool"),
        Tool(name="PctOfMaxTool"),
        Tool(name="CalculateAttemptsTool"),
        Tool(name="HealthRagSearchTool"),
        Tool(name="HealthGetCompetitionTool"),
        Tool(name="HealthListCompetitionsTool"),
        Tool(name="HealthGetDietNotesTool"),
        Tool(name="HealthGetSessionTool"),
        Tool(name="HealthGetSessionsRangeTool"),
        Tool(name="HealthGetSupplementsTool"),
        Tool(name="HealthGetMetaTool"),
        Tool(name="HealthGetPhasesTool"),
        Tool(name="HealthGetCurrentMaxesTool"),
        Tool(name="HealthGetGoalsTool"),
        Tool(name="HealthUpdateGoalsTool"),
        Tool(name="HealthGetFederationLibraryTool"),
        Tool(name="HealthUpdateFederationLibraryTool"),
        Tool(name="HealthGetOperatorPrefsTool"),
        Tool(name="HealthGetBreaksTool"),
        Tool(name="DaysUntilTool"),
        Tool(name="HealthUpdateCompetitionTool"),
        Tool(name="HealthSnapshotCompetitionProjectionTool"),
        Tool(name="HealthCompleteCompetitionTool"),
        Tool(name="HealthUpdateDietNoteTool"),
        Tool(name="HealthUpdateSupplementsTool"),
        Tool(name="HealthCreateSessionTool"),
        Tool(name="HealthDeleteSessionTool"),
        Tool(name="HealthRescheduleSessionTool"),
        Tool(name="HealthAddExerciseTool"),
        Tool(name="HealthRemoveExerciseTool"),
        Tool(name="HealthCreateCompetitionTool"),
        Tool(name="HealthDeleteCompetitionTool"),
        Tool(name="HealthDeleteDietNoteTool"),
        Tool(name="HealthUpdateMetaTool"),
        Tool(name="HealthUpdatePhasesTool"),
        Tool(name="HealthUpdateCurrentMaxesTool"),
        Tool(name="ExportProgramHistoryTool"),
        Tool(name="AnalyzeProgressionTool"),
        Tool(name="AnalyzeRpeDriftTool"),
        Tool(name="Estimate1rmTool"),
        Tool(name="CalculateDotsTool"),
        Tool(name="WeeklyAnalysisTool"),
        Tool(name="CorrelationAnalysisTool"),
        Tool(name="FatigueProfileEstimateTool"),
        Tool(name="MuscleGroupEstimateTool"),
        Tool(name="GlossaryGenerateTextTool"),
        Tool(name="LiftProfileReviewTool"),
        Tool(name="LiftProfileRewriteEstimateTool"),
        Tool(name="ProgramEvaluationTool"),
        Tool(name="ImportParseFileTool"),
        Tool(name="ImportApplyTool"),
        Tool(name="ImportRejectTool"),
        Tool(name="ImportListPendingTool"),
        Tool(name="ImportGetPendingTool"),
        Tool(name="TemplateListTool"),
        Tool(name="TemplateGetTool"),
        Tool(name="TemplateApplyTool"),
        Tool(name="TemplateApplyConfirmTool"),
        Tool(name="TemplateEvaluateTool"),
        Tool(name="TemplateCreateFromBlockTool"),
        Tool(name="TemplateCopyTool"),
        Tool(name="TemplateArchiveTool"),
        Tool(name="TemplateUnarchiveTool"),
        Tool(name="TemplateCreateBlankTool"),
        Tool(name="TemplateUpdateTool"),
        Tool(name="ProgramArchiveTool"),
        Tool(name="ProgramUnarchiveTool"),
        Tool(name="GlossaryAddTool"),
        Tool(name="GlossaryUpdateTool"),
        Tool(name="GlossarySetE1rmTool"),
        Tool(name="GlossaryEstimateE1rmTool"),
        Tool(name="GlossaryEstimateFatigueTool"),
        Tool(name="GlossaryEstimateMusclesTool"),
        Tool(name="PowerliftingFilterCategoriesTool"),
        Tool(name="AnalyzePowerliftingStatsTool"),
    ]


# =============================================================================
# Plugin contract: get_schemas() — JSON schemas for non-agentic specialist path
# =============================================================================

def get_schemas() -> Dict[str, Dict[str, Any]]:
    """Return snake_case tool name → JSON schema mapping."""
    return {
        "export_program_history": {
            "name": "export_program_history",
            "description": (
                "Export the full training program to an Excel (.xlsx) or Markdown (.md) file, including "
                "Lift Profiles, Weekly Analysis, Per-Lift Metrics, ROI Correlation, "
                "and Program Evaluation sections alongside the base program sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "description": "Export format: 'xlsx' or 'markdown'", "default": "xlsx"},
                },
                "required": [],
            },
        },
        "export_program_markdown": {
            "name": "export_program_markdown",
            "description": (
                "Generate the markdown export of the current program and return its content as a string. "
                "Used internally by regenerate_analysis."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "regenerate_analysis": {
            "name": "regenerate_analysis",
            "description": (
                "Regenerate deterministic current-block analysis caches: 6 weekly windows and the "
                "markdown export. Call this when the operator asks to refresh or regenerate their "
                "training analysis. This intentionally does not regenerate AI correlation reports, "
                "AI program evaluation, past-block caches, or the lifetime compare AI cache."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "get_analysis_markdown": {
            "name": "get_analysis_markdown",
            "description": (
                "Return the cached markdown export of the full training program (current block). "
                "This is the primary reference document for coaching decisions. "
                "Use the cache unless it is stale, dirty, or refresh is true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {"type": "boolean", "description": "Force regeneration before returning markdown", "default": False},
                    "max_age_hours": {"type": "integer", "description": "Maximum cache age before regeneration", "default": 72},
                },
                "required": [],
            },
        },
        "health_get_program": {
            "name": "health_get_program",
            "description": (
                "Get the full training program from DynamoDB. "
                "Returns the cached program dict with all sessions, phases, meta, and preferences."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_setup_status": {
            "name": "health_setup_status",
            "description": "Return no-data onboarding setup state for the active training data partition.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_setup_initialize": {
            "name": "health_setup_initialize",
            "description": "Initialize the first valid current training block for a no-data user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "blank, manual_sessions, or template"},
                    "program_name": {"type": "string", "description": "Optional program/block name"},
                    "start_date": {"type": "string", "description": "Program start date (YYYY-MM-DD)"},
                    "week_start_day": {"type": "string", "description": "Week start day, e.g. Monday"},
                    "template_sk": {"type": "string", "description": "Required when mode=template"},
                    "maxes": {"type": "object", "description": "Optional maxes/e1RMs keyed by squat, bench, deadlift, or template glossary IDs"},
                },
                "required": ["mode", "start_date", "week_start_day"],
            },
        },
        "health_get_session": {
            "name": "health_get_session",
            "description": "Get a single training session by date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Session date (YYYY-MM-DD)"},
                },
                "required": ["date"],
            },
        },
        "health_update_session": {
            "name": "health_update_session",
            "description": "Update fields on an existing training session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO8601 date string (YYYY-MM-DD) of the session to update"},
                    "patch": {"type": "object", "description": "Dict with session fields to update. Allowed keys: completed, session_rpe, body_weight_kg, session_notes, exercises"},
                },
                "required": ["date", "patch"],
            },
        },
        "health_new_version": {
            "name": "health_new_version",
            "description": "Create a new program version with the given patches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "change_reason": {"type": "string", "description": "Human-readable reason for the version change"},
                    "patches": {"type": "array", "items": {"type": "object"}, "description": "List of patches, each with 'path' and 'value' keys"},
                },
                "required": ["change_reason", "patches"],
            },
        },
        "health_rag_search": {
            "name": "health_rag_search",
            "description": "Search health documents using RAG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for health documents"},
                    "n_results": {"type": "integer", "description": "Number of results to return", "default": 4},
                },
                "required": ["query"],
            },
        },
        "health_get_competition": {
            "name": "health_get_competition",
            "description": "Get competition details by date.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "Competition date (YYYY-MM-DD)"}},
                "required": ["date"],
            },
        },
        "health_get_diet_notes": {
            "name": "health_get_diet_notes",
            "description": "Get diet notes for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start of date range (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End of date range (YYYY-MM-DD)"},
                },
                "required": [],
            },
        },
        "health_get_sessions_range": {
            "name": "health_get_sessions_range",
            "description": "Get training sessions for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start of date range (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End of date range (YYYY-MM-DD)"},
                },
                "required": ["start_date", "end_date"],
            },
        },
        "health_get_supplements": {
            "name": "health_get_supplements",
            "description": "Get the supplement protocol from the program.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_get_meta": {
            "name": "health_get_meta",
            "description": "Get program metadata (name, dates, weight class, etc.).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_get_phases": {
            "name": "health_get_phases",
            "description": "Get the training phases from the program.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_get_current_maxes": {
            "name": "health_get_current_maxes",
            "description": "Get current training maxes (squat, bench, deadlift).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_get_goals": {
            "name": "health_get_goals",
            "description": "Get the explicit goals for the current training block.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_update_goals": {
            "name": "health_update_goals",
            "description": "Replace the explicit goals array for the current training block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goals": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Complete goals array to write to the current block",
                    },
                },
                "required": ["goals"],
            },
        },
        "health_get_federation_library": {
            "name": "health_get_federation_library",
            "description": "Get the shared federation and qualification-standards library.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "health_update_federation_library": {
            "name": "health_update_federation_library",
            "description": "Replace the shared federation-library document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "federations": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Complete federation records array",
                    },
                    "qualification_standards": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Complete qualification standards array",
                    },
                },
                "required": ["federations", "qualification_standards"],
            },
        },
        "health_update_competition": {
            "name": "health_update_competition",
            "description": "Update competition fields by date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Competition date to update (YYYY-MM-DD)"},
                    "patch": {"type": "object", "description": "Fields to update (targets, status, notes, etc.)"},
                },
                "required": ["date", "patch"],
            },
        },
        "health_snapshot_competition_projection": {
            "name": "health_snapshot_competition_projection",
            "description": "Snapshot projected maxes 7 days before a competition and optionally backfill missed snapshots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Snapshot date (YYYY-MM-DD)"},
                    "version": {"type": "string", "description": "Program version to update", "default": "current"},
                    "allow_retrospective": {"type": "boolean", "description": "Allow backfilling a missed snapshot", "default": False},
                },
                "required": ["date"],
            },
        },
        "health_complete_competition": {
            "name": "health_complete_competition",
            "description": "Mark a competition as completed and compute PRR from the stored snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Competition date to complete (YYYY-MM-DD)"},
                    "results": {"type": "object", "description": "Best successful lift attempts and total"},
                    "body_weight_kg": {"type": "number", "description": "Official weigh-in bodyweight in kg"},
                    "post_meet_report": {"type": "object", "description": "Optional structured post-meet attempt and context report"},
                    "version": {"type": "string", "description": "Program version to update", "default": "current"},
                    "allow_retrospective": {"type": "boolean", "description": "Allow backfilling a missing T-1 snapshot", "default": True},
                },
                "required": ["date", "results", "body_weight_kg"],
            },
        },
        "health_update_diet_note": {
            "name": "health_update_diet_note",
            "description": "Create or replace a diet note for a date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date for the diet note (YYYY-MM-DD)"},
                    "notes": {"type": "string", "description": "The diet notes content"},
                },
                "required": ["date", "notes"],
            },
        },
        "health_update_supplements": {
            "name": "health_update_supplements",
            "description": "Update the supplement protocol.",
            "parameters": {
                "type": "object",
                "properties": {"patch": {"type": "object", 'description': '{"supplements": [...]} or {"supplement_phases": [...]}'},},
                "required": ["patch"],
            },
        },
        "health_create_session": {
            "name": "health_create_session",
            "description": "Create a new training session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Session date (YYYY-MM-DD)"},
                    "day": {"type": "string", "description": "Day label e.g. Monday"},
                    "week_number": {"type": "integer", "description": "Training week number"},
                    "exercises": {"type": "array", "items": {"type": "object"}, "description": "Optional list of exercises"},
                    "session_notes": {"type": "string", "description": "Optional session notes", "default": ""},
                },
                "required": ["date", "day", "week_number"],
            },
        },
        "health_delete_session": {
            "name": "health_delete_session",
            "description": "Delete a training session by date.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "Session date to delete (YYYY-MM-DD)"}},
                "required": ["date"],
            },
        },
        "health_reschedule_session": {
            "name": "health_reschedule_session",
            "description": "Move a training session from one date to another.",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_date": {"type": "string", "description": "Current session date (YYYY-MM-DD)"},
                    "new_date": {"type": "string", "description": "Target date to move to (YYYY-MM-DD)"},
                },
                "required": ["old_date", "new_date"],
            },
        },
        "health_add_exercise": {
            "name": "health_add_exercise",
            "description": "Add an exercise to a training session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Session date (YYYY-MM-DD)"},
                    "exercise": {"type": "object", "description": "Exercise dict: {name, sets, reps, kg, rpe, notes}"},
                },
                "required": ["date", "exercise"],
            },
        },
        "health_remove_exercise": {
            "name": "health_remove_exercise",
            "description": "Remove an exercise from a training session by index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Session date (YYYY-MM-DD)"},
                    "exercise_index": {"type": "integer", "description": "Zero-based index of the exercise to remove"},
                },
                "required": ["date", "exercise_index"],
            },
        },
        "health_create_competition": {
            "name": "health_create_competition",
            "description": "Create a new competition entry.",
            "parameters": {
                "type": "object",
                "properties": {"competition": {"type": "object", "description": "Competition dict: name, date, federation, federation_id, counts_toward_federation_ids, status, weight_class_kg, location, targets, notes"}},
                "required": ["competition"],
            },
        },
        "health_delete_competition": {
            "name": "health_delete_competition",
            "description": "Delete a competition entry by date.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "Competition date to delete (YYYY-MM-DD)"}},
                "required": ["date"],
            },
        },
        "health_delete_diet_note": {
            "name": "health_delete_diet_note",
            "description": "Delete a diet note by date.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "Diet note date to delete (YYYY-MM-DD)"}},
                "required": ["date"],
            },
        },
        "health_update_meta": {
            "name": "health_update_meta",
            "description": "Update program metadata fields, including sex for DOTS calculations.",
            "parameters": {
                "type": "object",
                "properties": {"updates": {"type": "object", "description": "Dict of meta fields to update"}},
                "required": ["updates"],
            },
        },
        "health_update_phases": {
            "name": "health_update_phases",
            "description": "Replace the full phases list.",
            "parameters": {
                "type": "object",
                "properties": {"phases": {"type": "array", "items": {"type": "object"}, "description": "Complete phases list. Each: {name, start_week, end_week, intent}"}},
                "required": ["phases"],
            },
        },
        "health_update_current_maxes": {
            "name": "health_update_current_maxes",
            "description": "Update current training maxes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "squat_kg": {"type": "number", "description": "New squat max in kg"},
                    "bench_kg": {"type": "number", "description": "New bench max in kg"},
                    "deadlift_kg": {"type": "number", "description": "New deadlift max in kg"},
                },
                "required": [],
            },
        },
        "kg_to_lb": {
            "name": "kg_to_lb",
            "description": "Convert kilograms to pounds.",
            "parameters": {"type": "object", "properties": {"kg": {"type": "number", "description": "Weight in kilograms"}}, "required": ["kg"]},
        },
        "lb_to_kg": {
            "name": "lb_to_kg",
            "description": "Convert pounds to kilograms.",
            "parameters": {"type": "object", "properties": {"lb": {"type": "number", "description": "Weight in pounds"}}, "required": ["lb"]},
        },
        "ipf_weight_classes": {
            "name": "ipf_weight_classes",
            "description": "Get IPF weight classes for a given sex.",
            "parameters": {"type": "object", "properties": {"sex": {"type": "string", "description": "Sex: 'M' or 'F'"}}, "required": ["sex"]},
        },
        "pct_of_max": {
            "name": "pct_of_max",
            "description": "Calculate a percentage of a max weight.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_kg": {"type": "number", "description": "Maximum weight in kg"},
                    "pct": {"type": "number", "description": "Percentage (0-150, not 0-1)"},
                },
                "required": ["max_kg", "pct"],
            },
        },
        "calculate_attempts": {
            "name": "calculate_attempts",
            "description": "Calculate competition attempt weights based on opener.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lift": {"type": "string", "description": "Lift type: squat, bench, or deadlift"},
                    "opener_kg": {"type": "number", "description": "First attempt weight in kg"},
                    "j1_override": {"type": "number", "description": "Override jump 1 from program prefs (kg)"},
                    "j2_override": {"type": "number", "description": "Override jump 2 from program prefs (kg)"},
                    "last_felt": {"type": "string", "description": "If 'hard', halve j2 for conservative third attempt"},
                },
                "required": ["lift", "opener_kg"],
            },
        },
        "days_until": {
            "name": "days_until",
            "description": "Calculate days until a target date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {"type": "string", "description": "Target date (YYYY-MM-DD)"},
                    "label": {"type": "string", "description": "Human label for the milestone", "default": "target"},
                },
                "required": ["target_date"],
            },
        },
        "export_program_history": {
            "name": "export_program_history",
            "description": (
                "Export the full training program to an Excel (.xlsx) or Markdown (.md) file. "
                "Sheets: Meta, Current Maxes, Phases, Sessions, Exercises, Competitions, "
                "Lift Profiles, Weekly Analysis, Per-Lift Metrics, ROI Correlation, Program Evaluation. "
                "The three AI-driven sheets use cached values; refresh on the Analysis page first if needed. "
                "After calling, emit a FILES: line to deliver the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "description": "Export format: 'xlsx' or 'markdown'", "default": "xlsx"},
                },
                "required": [],
            },
        },
        "analyze_progression": {
            "name": "analyze_progression",
            "description": (
                "Calculate weekly progression rate (kg/week) for a lift via Theil-Sen regression on top sets. "
                "Returns slope, Kendall tau, fit quality, and data points."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string", "description": "Name of the exercise"},
                    "weeks": {"type": "integer", "description": "Number of recent weeks to analyze"},
                },
                "required": ["exercise_name"],
            },
        },
        "analyze_rpe_drift": {
            "name": "analyze_rpe_drift",
            "description": (
                "Detect RPE drift for a lift — whether perceived exertion is trending up (fatigue) or down (adaptation)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string", "description": "Name of the exercise"},
                    "window_weeks": {"type": "integer", "description": "Number of weeks to analyze", "default": 4},
                },
                "required": ["exercise_name"],
            },
        },
        "estimate_1rm": {
            "name": "estimate_1rm",
            "description": "Estimate one-rep max using Epley, Brzycki, and RPE-based formulas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number", "description": "Weight lifted in kg"},
                    "reps": {"type": "integer", "description": "Number of repetitions"},
                    "rpe": {"type": "integer", "description": "RPE of the set (6-10)"},
                },
                "required": ["weight_kg", "reps"],
            },
        },
        "calculate_dots": {
            "name": "calculate_dots",
            "description": "Calculate DOTS score from competition total and bodyweight.",
            "parameters": {
                "type": "object",
                "properties": {
                    "total_kg": {"type": "number", "description": "Combined squat + bench + deadlift total"},
                    "bodyweight_kg": {"type": "number", "description": "Lifter bodyweight in kg"},
                    "sex": {"type": "string", "description": "'male' or 'female'"},
                },
                "required": ["total_kg", "bodyweight_kg", "sex"],
            },
        },
        "weekly_analysis": {
            "name": "weekly_analysis",
            "description": (
                "Full weekly training analysis — progression, RPE drift, fatigue index, "
                "compliance, meet projection. Returns structured JSON."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "integer", "description": "Number of weeks to analyze", "default": 1},
                    "block": {"type": "string", "description": "Program block filter", "default": "current"},
                    "week_start": {"type": "integer", "description": "Inclusive training week number to start analysis"},
                    "week_end": {"type": "integer", "description": "Inclusive training week number to end analysis"},
                    "window_start": {"type": "string", "description": "Optional date window start (YYYY-MM-DD) for time-series context"},
                    "window_end": {"type": "string", "description": "Optional date window end (YYYY-MM-DD) for time-series context"},
                    "ref_date": {"type": "string", "description": "Optional reference date (YYYY-MM-DD)"},
                    "refresh_program": {"type": "boolean", "description": "Invalidate the program cache before analysis", "default": True},
                    "program": {"type": "object", "description": "Optional program snapshot supplied by the caller"},
                    "sessions": {"type": "array", "description": "Optional session snapshot supplied by the caller", "items": {"type": "object"}},
                },
                "required": [],
            },
        },
        "analysis_section": {
            "name": "analysis_section",
            "description": (
                "Compute one weekly analysis section only. Use this for asynchronous section caches; "
                "it does not build the full weekly analysis report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["overview", "fatigue_readiness", "peaking", "workload", "alerts"],
                        "description": "The individual analysis section to compute",
                    },
                    "weeks": {"type": "integer", "description": "Number of weeks to analyze", "default": 1},
                    "block": {"type": "string", "description": "Program block filter", "default": "current"},
                    "week_start": {"type": "integer", "description": "Inclusive training week number to start analysis"},
                    "week_end": {"type": "integer", "description": "Inclusive training week number to end analysis"},
                    "window_start": {"type": "string", "description": "Optional date window start (YYYY-MM-DD) for time-series context"},
                    "window_end": {"type": "string", "description": "Optional date window end (YYYY-MM-DD) for time-series context"},
                    "ref_date": {"type": "string", "description": "Optional reference date (YYYY-MM-DD)"},
                    "refresh_program": {"type": "boolean", "description": "Invalidate the program cache before analysis", "default": True},
                    "program": {"type": "object", "description": "Optional program snapshot supplied by the caller"},
                    "sessions": {"type": "array", "description": "Optional session snapshot supplied by the caller", "items": {"type": "object"}},
                },
                "required": ["section"],
            },
        },
        "health_invalidate_program_cache": {
            "name": "health_invalidate_program_cache",
            "description": "Clear the in-memory cached training program so the next read loads from DynamoDB.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "correlation_analysis": {
            "name": "correlation_analysis",
            "description": (
                "AI-powered exercise ROI correlation analysis. Identifies which accessory "
                "exercises correlate with improvements in squat/bench/deadlift over a rolling "
                "window. Results are cached in DynamoDB. Use refresh=true to force regeneration."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "integer", "description": "Rolling window in weeks", "default": 4},
                    "block": {"type": "string", "description": "Program block filter", "default": "current"},
                    "refresh": {"type": "boolean", "description": "Force regeneration, ignore cache", "default": False},
                    "cache_only": {"type": "boolean", "description": "Return only cached results without generating AI output", "default": False},
                },
                "required": [],
            },
        },
        "block_correlation_analysis": {
            "name": "block_correlation_analysis",
            "description": (
                "AI-powered exercise ROI correlation analysis for a supplied block snapshot. "
                "Use this for past blocks so the correlation uses that block's sessions rather than today's rolling window."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "integer", "description": "Block length in weeks", "default": 4},
                    "window_start": {"type": "string", "description": "Block start date (YYYY-MM-DD)"},
                    "program": {"type": "object", "description": "Block-scoped program snapshot"},
                    "sessions": {"type": "array", "items": {"type": "object"}, "description": "Block sessions"},
                },
                "required": ["program", "sessions"],
            },
        },
        "fatigue_profile_estimate": {
            "name": "fatigue_profile_estimate",
            "description": (
                "Estimate the fatigue profile (axial/neural/peripheral/systemic components) "
                "for an exercise using AI analysis of biomechanical characteristics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {
                        "type": "object",
                        "description": "Exercise metadata dict",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string"},
                            "equipment": {"type": "string"},
                            "primary_muscles": {"type": "array", "items": {"type": "string"}},
                            "secondary_muscles": {"type": "array", "items": {"type": "string"}},
                            "tertiary_muscles": {"type": "array", "items": {"type": "string"}},
                            "description": {"type": "string"},
                            "how_to_perform": {"type": "string"},
                            "why_do_it": {"type": "string"},
                        },
                    },
                },
                "required": ["exercise"],
            },
        },
        "muscle_group_estimate": {
            "name": "muscle_group_estimate",
            "description": (
                "Estimate the primary, secondary, and tertiary muscle groups for an exercise "
                "using AI analysis of the movement and the user's lift profiles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {
                        "type": "object",
                        "description": "Exercise metadata dict",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string"},
                            "equipment": {"type": "string"},
                            "primary_muscles": {"type": "array", "items": {"type": "string"}},
                            "secondary_muscles": {"type": "array", "items": {"type": "string"}},
                            "tertiary_muscles": {"type": "array", "items": {"type": "string"}},
                            "description": {"type": "string"},
                            "how_to_perform": {"type": "string"},
                            "why_do_it": {"type": "string"},
                        },
                    },
                    "lift_profiles": {
                        "type": "array",
                        "description": "Optional squat/bench/deadlift lift profiles to pass through to the estimator",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lift": {"type": "string"},
                                "style_notes": {"type": "string"},
                                "sticking_points": {"type": "string"},
                                "primary_muscle": {"type": "string"},
                                "volume_tolerance": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["exercise"],
            },
        },
        "glossary_generate_text": {
            "name": "glossary_generate_text",
            "description": "Generate concise editable glossary text for what an exercise is, how to perform it, and why to use it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {
                        "type": "object",
                        "description": "Exercise metadata dict",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string"},
                            "equipment": {"type": "string"},
                            "primary_muscles": {"type": "array", "items": {"type": "string"}},
                            "secondary_muscles": {"type": "array", "items": {"type": "string"}},
                            "tertiary_muscles": {"type": "array", "items": {"type": "string"}},
                            "description": {"type": "string"},
                            "how_to_perform": {"type": "string"},
                            "why_do_it": {"type": "string"},
                        },
                    },
                    "lift_profiles": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional squat/bench/deadlift lift profiles",
                    },
                },
                "required": ["exercise"],
            },
        },
        "lift_profile_review": {
            "name": "lift_profile_review",
            "description": (
                "Review a squat, bench, or deadlift style profile and return missing "
                "biomechanical details needed to estimate a lift-specific INOL stimulus coefficient."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": "Lift profile with lift, style_notes, sticking_points, primary_muscle, and volume_tolerance.",
                    },
                },
                "required": ["profile"],
            },
        },
        "lift_profile_rewrite_and_estimate": {
            "name": "lift_profile_rewrite_and_estimate",
            "description": (
                "Rewrite a lift style profile for analysis clarity and estimate a 1-2 "
                "INOL stimulus coefficient against a baseline of 1.0."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": "Lift profile with lift, style_notes, sticking_points, primary_muscle, and volume_tolerance.",
                    },
                },
                "required": ["profile"],
            },
        },
        "lift_profile_rewrite": {
            "name": "lift_profile_rewrite",
            "description": "Rewrite lift profile text for analysis clarity without estimating stimulus coefficient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": "Lift profile with lift, style_notes, sticking_points, primary_muscle, and volume_tolerance.",
                    },
                },
                "required": ["profile"],
            },
        },
        "lift_profile_estimate_stimulus": {
            "name": "lift_profile_estimate_stimulus",
            "description": (
                "Estimate a 1-2 INOL stimulus coefficient from an existing lift profile. "
                "Requires profile completeness score >= 55."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "description": "Lift profile with lift, style_notes, sticking_points, primary_muscle, and volume_tolerance.",
                    },
                },
                "required": ["profile"],
            },
        },
        "program_evaluation": {
            "name": "program_evaluation",
            "description": (
                "Full-block AI program evaluation by a sports scientist. "
                "Evaluates the current block against competition goals, identifies what is working and not, "
                "and suggests small targeted changes. "
                "Requires >= 4 completed weeks. Cached weekly. Use refresh=true to force regeneration."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {"type": "boolean", "description": "Force regeneration, ignore cache", "default": False},
                    "cache_only": {"type": "boolean", "description": "Return only cached results without generating AI output", "default": False},
                },
                "required": [],
            },
        },
        "block_program_evaluation": {
            "name": "block_program_evaluation",
            "description": (
                "AI program evaluation for a supplied historical block snapshot. "
                "The caller supplies a normalized program where the target block sessions are scoped to current. "
                "Use this for past-block program analysis without loading the live current program."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "program": {"type": "object", "description": "Block-scoped program snapshot to evaluate."},
                },
                "required": ["program"],
            },
        },
        "multi_block_comparison_analysis": {
            "name": "multi_block_comparison_analysis",
            "description": (
                "AI comparison of current and historical block analysis bundles. "
                "Identifies similarities, differences, lift-specific outcomes, ROI, volume dose response, "
                "bodyweight/training-day relationships, projection accuracy, fatigue patterns, and best-value blocks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object", "description": "Multi-block comparison payload built from block analytics."},
                },
                "required": ["payload"],
            },
        },
        "import_parse_file": {
            "name": "import_parse_file",
            "description": "Parse a spreadsheet file and stage it as a pending import.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base64_content": {"type": "string"},
                    "filename": {"type": "string"}
                },
                "required": ["base64_content", "filename"],
            },
        },
        "import_apply": {
            "name": "import_apply",
            "description": "Apply a staged import to the program or template library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "import_id": {"type": "string"},
                    "merge_strategy": {"type": "string", "default": "append"},
                    "conflict_resolutions": {"type": "array", "items": {"type": "object"}},
                    "start_date": {"type": "string"}
                },
                "required": ["import_id"],
            },
        },
        "import_reject": {
            "name": "import_reject",
            "description": "Reject a staged import.",
            "parameters": {
                "type": "object",
                "properties": {
                    "import_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["import_id"],
            },
        },
        "import_list_pending": {
            "name": "import_list_pending",
            "description": "List all awaiting_review imports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "import_type": {"type": "string"}
                },
                "required": [],
            },
        },
        "import_get_pending": {
            "name": "import_get_pending",
            "description": "Get a single pending import by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "import_id": {"type": "string"}
                },
                "required": ["import_id"],
            },
        },
        "template_list": {
            "name": "template_list",
            "description": "List all training templates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_archived": {"type": "boolean", "default": False},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition for draft visibility"}
                },
                "required": [],
            },
        },
        "template_get": {
            "name": "template_get",
            "description": "Get full training template structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition for draft visibility"}
                },
                "required": ["sk"],
            },
        },
        "template_apply": {
            "name": "template_apply",
            "description": "Apply a template to the program block (preview).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "target": {"type": "string", "default": "new_block"},
                    "start_date": {"type": "string"},
                    "week_start_day": {"type": "string", "default": "Monday"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition for draft visibility"}
                },
                "required": ["sk"],
            },
        },
        "template_apply_confirm": {
            "name": "template_apply_confirm",
            "description": "Confirm and write concretized block from template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "backfilled_maxes": {"type": "object"},
                    "start_date": {"type": "string"},
                    "week_start_day": {"type": "string"},
                    "target": {"type": "string", "description": "Apply strategy", "default": "new_block"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition for draft visibility"}
                },
                "required": ["sk"],
            },
        },
        "template_evaluate": {
            "name": "template_evaluate",
            "description": "Run AI-powered template evaluation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition for draft visibility"}
                },
                "required": ["sk"],
            },
        },
        "template_create_from_block": {
            "name": "template_create_from_block",
            "description": "Convert program block to template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "program_sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"},
                    "author": {"type": "string", "description": "Display author"}
                },
                "required": ["name"],
            },
        },
        "template_copy": {
            "name": "template_copy",
            "description": "Duplicate a template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "new_name": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"},
                    "author": {"type": "string", "description": "Display author"}
                },
                "required": ["sk", "new_name"],
            },
        },
        "template_archive": {
            "name": "template_archive",
            "description": "Archive a template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"}
                },
                "required": ["sk"],
            },
        },
        "template_unarchive": {
            "name": "template_unarchive",
            "description": "Unarchive a template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"}
                },
                "required": ["sk"],
            },
        },
        "template_publish": {
            "name": "template_publish",
            "description": "Publish an authored draft template so everyone can see and apply it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"}
                },
                "required": ["sk"],
            },
        },
        "template_unpublish": {
            "name": "template_unpublish",
            "description": "Unpublish an authored template so only its author can see it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"}
                },
                "required": ["sk"],
            },
        },
        "template_create_blank": {
            "name": "template_create_blank",
            "description": "Create a new blank training template with no sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string", "default": ""},
                    "estimated_weeks": {"type": "integer", "default": 4},
                    "days_per_week": {"type": "integer", "default": 3},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"},
                    "author": {"type": "string", "description": "Display author"},
                },
                "required": ["name"],
            },
        },
        "template_create_from_payload": {
            "name": "template_create_from_payload",
            "description": "Create a complete reusable training template atomically from a structured payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {"type": "object"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"},
                    "author": {"type": "string", "description": "Display author"},
                    "published": {"type": "boolean", "default": False},
                    "import_job_id": {"type": "string"}
                },
                "required": ["template"],
            },
        },
        "template_update": {
            "name": "template_update",
            "description": "Overwrite an existing training template in place (metadata, phases, sessions).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"},
                    "template": {"type": "object"},
                    "actor_pk": {"type": "string", "description": "Signed-in user/template author partition"},
                },
                "required": ["sk", "template"],
            },
        },
        "program_archive": {
            "name": "program_archive",
            "description": "Archive a program version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"}
                },
                "required": ["sk"],
            },
        },
        "program_unarchive": {
            "name": "program_unarchive",
            "description": "Unarchive a program version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string"}
                },
                "required": ["sk"],
            },
        },
        "glossary_add": {
            "name": "glossary_add",
            "description": "Add new exercise to glossary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "object"}
                },
                "required": ["exercise"],
            },
        },
        "glossary_update": {
            "name": "glossary_update",
            "description": "Update exercise in glossary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "fields": {"type": "object"}
                },
                "required": ["id", "fields"],
            },
        },
        "glossary_set_e1rm": {
            "name": "glossary_set_e1rm",
            "description": "Manually set e1RM for glossary exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "value_kg": {"type": "number"},
                    "method": {"type": "string"}
                },
                "required": ["id", "value_kg"],
            },
        },
        "glossary_estimate_e1rm": {
            "name": "glossary_estimate_e1rm",
            "description": "AI backfill e1RM estimate for one exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"],
            },
        },
        "glossary_estimate_fatigue": {
            "name": "glossary_estimate_fatigue",
            "description": "AI fatigue profile estimation for one exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"],
            },
        },
        "glossary_estimate_muscles": {
            "name": "glossary_estimate_muscles",
            "description": "AI muscle group estimation for one glossary exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"],
            },
        },
        "powerlifting_filter_categories": {
            "name": "powerlifting_filter_categories",
            "description": "Retrieves the unique options available for filtering the OpenPowerlifting dataset.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        "analyze_powerlifting_stats": {
            "name": "analyze_powerlifting_stats",
            "description": "Compares a user's powerlifting stats against the OpenPowerlifting dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "squat_kg": {"type": "number"},
                    "bench_kg": {"type": "number"},
                    "deadlift_kg": {"type": "number"},
                    "bodyweight_kg": {"type": "number"},
                    "sex_code": {"type": "string", "description": "User's sex for DOTS: 'M' or 'F'"},
                    "federation": {"type": "string"},
                    "country": {"type": "string"},
                    "region": {"type": "string"},
                    "equipment": {"type": "string"},
                    "sex": {"type": "string"},
                    "age_class": {"type": "string"},
                    "year": {"type": "integer"},
                    "event_type": {"type": "string"},
                    "min_dots": {"type": "number"}
                },
                "required": [],
            },
        },
        "powerlifting_ranking_percentile": {
            "name": "powerlifting_ranking_percentile",
            "description": (
                "Returns national/regional/global top-percentile cards for the dashboard. "
                "Filters the OpenPowerlifting dataset to the 3 nearest IPF weight classes, "
                "last 3 calendar years, deduplicated by lifter (best total per name). "
                "Returns percentile (0-100) for Squat/Bench/Deadlift/Total across global, "
                "national (country), and regional (country+region) scopes. "
                "A value is null when <10 comparison lifters or the lift was not provided."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "squat_kg": {"type": "number", "description": "User's best squat in kg"},
                    "bench_kg": {"type": "number", "description": "User's best bench in kg"},
                    "deadlift_kg": {"type": "number", "description": "User's best deadlift in kg"},
                    "bodyweight_kg": {"type": "number", "description": "User's bodyweight in kg"},
                    "sex_code": {"type": "string", "description": "'M' or 'F'"},
                    "country": {"type": "string", "description": "Filter national scope (MeetCountry value from dataset)"},
                    "region": {"type": "string", "description": "Filter regional scope (State value from dataset)"},
                    "age_class": {"type": "string", "description": "Filter by age class"},
                    "equipment": {"type": "string", "description": "Filter by equipment (e.g. Raw)"},
                },
                "required": [],
            },
        },
    }


# =============================================================================
# Route helpers for analytics/export tools (non-agentic specialist path)
# =============================================================================

def _get_program_and_sessions(refresh_program: bool = False):
    """Fetch program from store, return (program, sessions, program_start)."""
    from core import _get_store
    store = _get_store()
    if refresh_program:
        store.invalidate_cache()
    program = _run_async(store.get_program())
    sessions = program.get("sessions", [])
    program_start = program.get("meta", {}).get("program_start", "")
    return program, sessions, program_start


def _get_analysis_program_and_sessions(args: dict, refresh_program: bool = False):
    """Use caller-supplied snapshots when available; otherwise load from the store."""
    supplied_program = args.get("program")
    supplied_sessions = args.get("sessions")
    if isinstance(supplied_program, dict):
        program = dict(supplied_program)
        sessions = supplied_sessions if isinstance(supplied_sessions, list) else program.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        program["sessions"] = sessions
        program_start = program.get("meta", {}).get("program_start", "")
        return program, sessions, program_start

    return _get_program_and_sessions(refresh_program=refresh_program)


def _do_health_invalidate_program_cache(args):
    from core import _get_store
    _get_store().invalidate_cache()
    return {"success": True}


def _do_export(args):
    import json
    import os
    from config import SANDBOX_PATH
    from core import _get_store

    conversation_id = args.get("_conversation_id", "default")
    out_dir = os.path.join(SANDBOX_PATH, conversation_id)
    os.makedirs(out_dir, exist_ok=True)

    program = _run_async(_get_store().get_program())
    sessions = program.get("sessions", []) if isinstance(program, dict) else []
    filename, description, export_format = _write_program_export(program, sessions, out_dir, args.get("format"))

    payload = json.dumps({
        "filename": filename,
        "format": export_format,
        "message": "Program history exported successfully.",
    })
    return f"{payload}\nFILES: {filename} ({description})"


def _do_analyze_progression(args):
    from analytics import progression_rate
    program, sessions, program_start = _get_program_and_sessions()
    return progression_rate(sessions, args["exercise_name"], program_start)


def _do_analyze_rpe_drift(args):
    from analytics import rpe_drift
    program, sessions, program_start = _get_program_and_sessions()
    return rpe_drift(sessions, args["exercise_name"], program_start, args.get("window_weeks", 4))


def _do_estimate_1rm(args):
    from analytics import estimate_1rm
    return estimate_1rm(args["weight_kg"], args["reps"], args.get("rpe"))


def _do_calculate_dots(args):
    from analytics import calculate_dots
    return {"dots": calculate_dots(args["total_kg"], args["bodyweight_kg"], args["sex"])}


def _do_weekly_analysis(args):
    from config import IF_HEALTH_TABLE_NAME
    program, sessions, program_start = _get_analysis_program_and_sessions(
        args,
        refresh_program=args.get("refresh_program", True),
    )
    glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
    return _build_sectioned_analysis(
        program,
        sessions,
        glossary,
        weeks=args.get("weeks", 1),
        block=args.get("block", "current"),
        window_start=args.get("window_start"),
        window_end=args.get("window_end"),
        ref_date=args.get("ref_date"),
        week_start=args.get("week_start"),
        week_end=args.get("week_end"),
    )


def _do_analysis_section(args):
    from analytics import weekly_analysis_section
    from config import IF_HEALTH_TABLE_NAME
    program, sessions, program_start = _get_analysis_program_and_sessions(
        args,
        refresh_program=args.get("refresh_program", True),
    )
    glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
    return weekly_analysis_section(
        program,
        sessions,
        section=args["section"],
        window_start=args.get("window_start"),
        window_end=args.get("window_end"),
        ref_date=args.get("ref_date"),
        week_start=args.get("week_start"),
        week_end=args.get("week_end"),
        weeks=args.get("weeks", 1),
        block=args.get("block", "current"),
        glossary=glossary,
    )


def _do_correlation_analysis(args):
    from datetime import datetime, timedelta
    from core import _get_store
    from correlation_ai import generate_correlation_report
    from config import IF_HEALTH_TABLE_NAME
    import boto3

    weeks = args.get("weeks", 4)
    refresh = args.get("refresh", False)
    cache_only = args.get("cache_only", False)

    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    days_since_monday = raw_cutoff.weekday()
    window_start = raw_cutoff - timedelta(days=days_since_monday)
    window_start_str = window_start.isoformat()
    cache_sk = f"corr_report#{window_start_str}_{weeks}w"

    store = _get_store()
    active_pk = store.pk
    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(IF_HEALTH_TABLE_NAME)

    if not refresh:
        cached = table.get_item(Key={"pk": active_pk, "sk": cache_sk}).get("Item")
        if cached and cached.get("report"):
            report = cached["report"]
            if isinstance(report, dict):
                report["cached"] = True
                report["generated_at"] = cached.get("generated_at", "")
                report["window_start"] = window_start_str
                report["weeks"] = weeks
            return report

    if cache_only:
        return {
            "findings": [],
            "summary": "",
            "insufficient_data": True,
            "insufficient_data_reason": "No cached ROI correlation report exists. Generate it to run AI analysis.",
            "cache_miss": True,
            "cached": False,
            "generated_at": "",
            "window_start": window_start_str,
            "weeks": weeks,
        }

    store.invalidate_cache()
    program = _run_async(store.get_program())
    sessions = program.get("sessions", [])
    lift_profiles = program.get("lift_profiles", [])

    report = _run_async(generate_correlation_report(
        sessions=sessions,
        lift_profiles=lift_profiles,
        weeks=weeks,
        window_start=window_start_str,
        program=program,
    ))

    generated_at = datetime.utcnow().isoformat() + "Z"

    table.put_item(Item={
        "pk": active_pk,
        "sk": cache_sk,
        "report": report,
        "generated_at": generated_at,
        "window_start": window_start_str,
        "weeks": weeks,
    })

    report["cached"] = False
    report["generated_at"] = generated_at
    report["window_start"] = window_start_str
    report["weeks"] = weeks
    return report


def _do_block_correlation_analysis(args):
    from datetime import datetime
    from correlation_ai import generate_correlation_report

    program = args.get("program")
    sessions = args.get("sessions")
    weeks = args.get("weeks", 4)
    window_start = args.get("window_start", "")
    if not isinstance(program, dict) or not isinstance(sessions, list):
        return {
            "findings": [],
            "summary": "",
            "generated_at": "",
            "window_start": window_start,
            "weeks": weeks,
            "cached": False,
            "insufficient_data": True,
            "insufficient_data_reason": "A block-scoped program and sessions snapshot is required.",
        }

    report = _run_async(generate_correlation_report(
        sessions=sessions,
        lift_profiles=program.get("lift_profiles", []),
        weeks=weeks,
        window_start=window_start,
        program=program,
    ))
    if isinstance(report, dict):
        report["cached"] = False
        report["generated_at"] = datetime.utcnow().isoformat() + "Z"
        report["window_start"] = window_start
        report["weeks"] = weeks
    return report


def _fatigue_context():
    """Return (program_meta, lift_profiles) for fatigue estimation, or (None, None) on failure."""
    try:
        from core import _get_store
        program = _run_async(_get_store().get_program())
    except Exception:
        return None, None
    if not isinstance(program, dict):
        return None, None
    return program.get("meta") or None, program.get("lift_profiles") or None


def _do_fatigue_profile_estimate(args):
    from fatigue_ai import estimate_fatigue_profile
    program_meta, lift_profiles = _fatigue_context()
    return _run_async(estimate_fatigue_profile(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    ))


def _do_muscle_group_estimate(args):
    from muscle_group_ai import estimate_muscle_groups
    program_meta, stored_lift_profiles = _fatigue_context()
    lift_profiles = args.get("lift_profiles")
    if not isinstance(lift_profiles, list) or not lift_profiles:
        lift_profiles = stored_lift_profiles
    return _run_async(estimate_muscle_groups(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    ))


def _do_glossary_generate_text(args):
    from glossary_text_ai import generate_glossary_text
    _, stored_lift_profiles = _fatigue_context()
    lift_profiles = args.get("lift_profiles")
    if not isinstance(lift_profiles, list) or not lift_profiles:
        lift_profiles = stored_lift_profiles
    return _run_async(generate_glossary_text(
        args["exercise"],
        lift_profiles=lift_profiles,
    ))


def _do_lift_profile_review(args):
    from lift_profile_ai import review_lift_profile
    return _run_async(review_lift_profile(args["profile"]))


def _do_lift_profile_rewrite_and_estimate(args):
    from lift_profile_ai import rewrite_and_estimate_lift_profile
    return _run_async(rewrite_and_estimate_lift_profile(args["profile"]))


def _do_lift_profile_rewrite(args):
    from lift_profile_ai import rewrite_lift_profile
    return _run_async(rewrite_lift_profile(args["profile"]))


def _do_lift_profile_estimate_stimulus(args):
    from lift_profile_ai import estimate_lift_profile_stimulus
    return _run_async(estimate_lift_profile_stimulus(args["profile"]))


def _do_program_evaluation(args):
    from core import health_program_evaluation
    return _run_async(health_program_evaluation(refresh=args.get("refresh", False), cache_only=args.get("cache_only", False)))


def _do_block_program_evaluation(args):
    from program_evaluation_ai import generate_program_evaluation_report

    program = args.get("program")
    if not isinstance(program, dict):
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "A block-scoped program snapshot is required.",
            "cached": False,
            "generated_at": "",
            "window_start": "",
            "weeks": 0,
        }

    federation_library = None
    try:
        from core import _get_federation_store
        federation_library = _run_async(_get_federation_store().get_library())
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("block_program_evaluation: federation library unavailable: %s", exc)

    return _run_async(generate_program_evaluation_report(
        program,
        federation_library=federation_library,
    ))


def _do_multi_block_comparison_analysis(args):
    from multi_block_comparison_ai import generate_multi_block_comparison_report

    payload = args.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return _run_async(generate_multi_block_comparison_report(payload))


def _do_powerlifting_filter_categories(args):
    from powerlifting_stats import load_data, get_filter_categories, DatasetNotReadyError
    try:
        df = load_data()
        return get_filter_categories(df)
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"


def _do_analyze_powerlifting_stats(args):
    from powerlifting_stats import load_data, filter_dataset, analyze_stats, DatasetNotReadyError
    try:
        df = load_data()
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"
        
    filtered_df = filter_dataset(
        df,
        federation=args.get("federation"),
        country=args.get("country"),
        region=args.get("region"),
        equipment=args.get("equipment"),
        sex=args.get("sex"),
        age_class=args.get("age_class"),
        year=args.get("year"),
        event_type=args.get("event_type"),
        min_dots=args.get("min_dots"),
    )
    return analyze_stats(
        filtered_df,
         squat_kg=args.get("squat_kg"),
         bench_kg=args.get("bench_kg"),
         deadlift_kg=args.get("deadlift_kg"),
         bodyweight_kg=args.get("bodyweight_kg"),
         sex_code=args.get("sex_code"),
     )


def _do_powerlifting_ranking_percentile(args):
    from powerlifting_stats import load_data, compute_ranking_percentiles, DatasetNotReadyError
    try:
        df = load_data()
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"
    return compute_ranking_percentiles(
        df,
        squat_kg=args.get("squat_kg"),
        bench_kg=args.get("bench_kg"),
        deadlift_kg=args.get("deadlift_kg"),
        bodyweight_kg=args.get("bodyweight_kg"),
        sex_code=args.get("sex_code"),
        country=args.get("country"),
        region=args.get("region"),
        age_class=args.get("age_class"),
        equipment=args.get("equipment"),
    )


def _do_export_program_markdown(args: Dict[str, Any]) -> str:
    """Generate a markdown export of the current program and return its content as a string."""
    import os
    import tempfile
    from core import _get_store
    from export import build_program_markdown

    program = _run_async(_get_store().get_program())
    sessions = program.get("sessions", []) if isinstance(program, dict) else []
    analysis = _build_analysis_bundle(program, sessions)
    scoped_program = _scope_program_to_current_block(program)
    out_path = os.path.join(tempfile.gettempdir(), "program_history_cache.md")
    build_program_markdown(scoped_program, out_path, analysis=analysis, export_context=analysis)
    with open(out_path, "r", encoding="utf-8") as f:
        markdown = f.read()
    return {"markdown": markdown, "length": len(markdown)}


_DETERMINISTIC_ANALYSIS_SECTIONS = ["overview", "fatigue_readiness", "peaking", "workload", "alerts"]


def _build_sectioned_week_analysis(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None,
    *,
    week_start: int,
    week_end: int,
    ref_date: str,
) -> dict:
    return _build_sectioned_analysis(
        program,
        sessions,
        glossary,
        weeks=max(1, week_end - week_start + 1),
        block="current",
        week_start=week_start,
        week_end=week_end,
        ref_date=ref_date,
    )


def _build_sectioned_analysis(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None,
    *,
    weeks: int = 1,
    block: str = "current",
    window_start: str | None = None,
    window_end: str | None = None,
    ref_date: str | None = None,
    week_start: int | None = None,
    week_end: int | None = None,
) -> dict:
    from analytics import weekly_analysis_section

    result: dict[str, Any] = {}
    for section in _DETERMINISTIC_ANALYSIS_SECTIONS:
        result.update(weekly_analysis_section(
            program=program,
            sessions=sessions,
            section=section,
            weeks=weeks,
            block=block,
            window_start=window_start,
            window_end=window_end,
            week_start=week_start,
            week_end=week_end,
            ref_date=ref_date,
            glossary=glossary,
        ))
    return result


async def _do_regenerate_analysis(args: Dict[str, Any]) -> Dict[str, Any]:
    """Regenerate deterministic current-block analysis caches and markdown export.

    AI reports are intentionally excluded; they are regenerated only through
    explicit AI section tools because those calls are comparatively expensive.
    NEVER touches past-block caches.
    """
    import os
    import json
    import tempfile
    import time as _time
    import boto3
    from datetime import datetime
    from core import _get_store, _floats_to_decimals
    from export import build_program_markdown

    from config import ANALYSIS_CACHE_TABLE_NAME, AWS_REGION

    store = _get_store()
    store.invalidate_cache()
    program = await store.get_program()
    pk = store.pk
    sessions = program.get("sessions", [])
    glossary = _run_async(_get_glossary_store().get_glossary()) if hasattr(_get_glossary_store(), "get_glossary") else []

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(ANALYSIS_CACHE_TABLE_NAME)
    cache_pk = f"analysis#{pk}"
    expires_at = int(_time.time()) + 7 * 86400

    # Build analysis windows from program (replicate TypeScript buildAnalysisWindows logic)
    program_start = (program.get("meta") or {}).get("program_start") or next(
        (s.get("date") for s in sessions if (s.get("block") or "current") == "current"), None
    ) or datetime.utcnow().date().isoformat()

    current_sessions = [s for s in sessions if (s.get("block") or "current") == "current"]
    # Sort by week_number to find current week
    current_week = max(
        (int(s.get("week_number", 0)) for s in current_sessions if s.get("week_number")),
        default=1
    )

    window_specs = [
        ("current", current_week, current_week),
        ("previous_1", max(1, current_week - 1), current_week),
        ("previous_2", max(1, current_week - 2), current_week),
        ("previous_4", max(1, current_week - 4), current_week),
        ("previous_8", max(1, current_week - 8), current_week),
        ("block", 1, current_week),
    ]

    today_iso = datetime.utcnow().date().isoformat()
    errors = []
    block_analysis_result = None

    for window_key, week_start, week_end in window_specs:
        try:
            result = _build_sectioned_week_analysis(
                program,
                sessions,
                glossary,
                week_start=week_start,
                week_end=week_end,
                ref_date=today_iso,
            )
            if window_key == "block":
                block_analysis_result = result

            payload_str = json.dumps(result)
            sk = f"weekly_analysis#{window_key}"
            item = {
                "pk": cache_pk,
                "sk": sk,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at,
                "payload": payload_str,
            }
            table.put_item(Item=_floats_to_decimals(item))
        except Exception as exc:
            errors.append(f"window {window_key}: {exc}")

    # Generate markdown export
    try:
        out_path = os.path.join(tempfile.gettempdir(), "program_history_regen.md")
        scoped_program = _scope_program_to_current_block(program)
        analysis_bundle = {
            "weekly": block_analysis_result or {},
            "pk": pk,
            "sex": str((program.get("meta") or {}).get("sex") or "male").lower(),
        }
        build_program_markdown(scoped_program, out_path, analysis=analysis_bundle, export_context=analysis_bundle)
        with open(out_path, "r", encoding="utf-8") as f:
            markdown = f.read()
        if markdown:
            md_item = {
                "pk": cache_pk,
                "sk": "markdown_export#current",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at,
                "payload": json.dumps({"markdown": markdown}),
            }
            table.put_item(Item=_floats_to_decimals(md_item))
            try:
                from cache_invalidation import clear_markdown_export_dirty
                clear_markdown_export_dirty(pk, ANALYSIS_CACHE_TABLE_NAME, AWS_REGION)
            except Exception:
                pass
    except Exception as exc:
        errors.append(f"markdown_export: {exc}")

    return {
        "success": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "windows_regenerated": 6,
        "errors": errors,
        "message": (
            f"Regenerated 6 deterministic analysis windows from individual section calculations and markdown export. AI reports were not regenerated."
            + (f" {len(errors)} non-fatal errors: {'; '.join(errors)}" if errors else "")
        ),
    }


def _do_get_analysis_markdown(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return cached markdown export, regenerating only when stale or dirty."""
    import json
    import time as _time
    import boto3
    from datetime import datetime, timezone
    from core import _get_store, _floats_to_decimals
    from export import build_program_markdown
    import tempfile
    import os

    from config import ANALYSIS_CACHE_TABLE_NAME, AWS_REGION

    store = _get_store()
    pk = store.pk
    cache_pk = f"analysis#{pk}"
    max_age_hours = int(args.get("max_age_hours") or 72)
    force_refresh = bool(args.get("refresh") or args.get("force_refresh"))

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(ANALYSIS_CACHE_TABLE_NAME)

    def _parse_generated_at(value: str | None):
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    try:
        from analysis_cache import AnalysisCacheStore

        cache_store = AnalysisCacheStore(
            table_name=ANALYSIS_CACHE_TABLE_NAME,
            pk=pk,
            region=AWS_REGION,
        )
        cached = cache_store.get_markdown_cache("current")
        dirty = cache_store.get_markdown_dirty("current")
        generated_at_dt = _parse_generated_at(cached.get("generated_at") if cached else None)
        fresh_enough = (
            generated_at_dt is not None
            and (datetime.now(timezone.utc) - generated_at_dt).total_seconds() <= max_age_hours * 3600
        )
        if cached and fresh_enough and not dirty and not force_refresh:
            return {
                "markdown": cached["markdown"],
                "generated_at": cached.get("generated_at", ""),
                "cached": True,
                "dirty": False,
            }

        regen = _run_async(_do_regenerate_analysis({"pk": pk}))
        refreshed = cache_store.get_markdown_cache("current")
        if refreshed and refreshed.get("markdown"):
            cache_store.clear_markdown_dirty("current")
            return {
                "markdown": refreshed["markdown"],
                "generated_at": refreshed.get("generated_at", regen.get("generated_at", "")),
                "cached": False,
                "dirty": False,
                "regenerated": True,
            }
    except Exception as exc:
        logging.getLogger(__name__).warning("get_analysis_markdown cache path failed: %s", exc)

    # Fallback: generate fresh markdown in-process if the cache path failed.
    store.invalidate_cache()
    program = _run_async(store.get_program())
    sessions = [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]
    today_iso = datetime.utcnow().date().isoformat()
    current_week = max(
        (int(s.get("week_number", 0)) for s in sessions if s.get("week_number")),
        default=1,
    )
    glossary = _run_async(_get_glossary_store().get_glossary()) if hasattr(_get_glossary_store(), "get_glossary") else []
    analysis = _build_sectioned_week_analysis(
        program,
        sessions,
        glossary,
        week_start=1,
        week_end=current_week,
        ref_date=today_iso,
    )
    scoped_program = _scope_program_to_current_block(program)
    out_path = os.path.join(tempfile.gettempdir(), "program_history_live.md")
    analysis_bundle = {
        "weekly": analysis,
        "pk": pk,
        "sex": str((program.get("meta") or {}).get("sex") or "male").lower(),
    }
    build_program_markdown(scoped_program, out_path, analysis=analysis_bundle, export_context=analysis_bundle)
    with open(out_path, "r", encoding="utf-8") as f:
        markdown = f.read()

    generated_at = datetime.utcnow().isoformat() + "Z"
    expires_at = int(_time.time()) + 7 * 86400
    try:
        table.put_item(Item=_floats_to_decimals({
            "pk": cache_pk,
            "sk": "markdown_export#current",
            "generated_at": generated_at,
            "expires_at": expires_at,
            "payload": json.dumps({"markdown": markdown}),
        }))
    except Exception:
        pass

    return {"markdown": markdown, "generated_at": generated_at, "cached": False}


# =============================================================================
# Plugin contract: execute() — async dispatcher for non-agentic specialist path
# =============================================================================

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route health tool calls to the underlying health module functions."""
    from core import(
        health_get_program,
        health_setup_status,
        health_setup_initialize,
        health_get_session,
        health_update_session as do_update_session,
        health_rag_search,
        health_get_competition,
        health_get_diet_notes,
        health_get_sessions_range,
        health_get_supplements,
        health_get_meta,
        health_get_phases,
        health_get_current_maxes,
        health_get_goals,
        health_update_goals as do_update_goals,
        health_get_federation_library,
        health_update_federation_library as do_update_federation_library,
        health_update_competition as do_update_competition,
        health_snapshot_competition_projection as do_snapshot_competition_projection,
        health_complete_competition as do_complete_competition,
        health_update_diet_note as do_update_diet_note,
        health_update_supplements as do_update_supplements,
        health_create_session as do_create_session,
        health_delete_session as do_delete_session,
        health_reschedule_session as do_reschedule_session,
        health_add_exercise as do_add_exercise,
        health_remove_exercise as do_remove_exercise,
        health_create_competition as do_create_competition,
        health_delete_competition as do_delete_competition,
        health_delete_diet_note as do_delete_diet_note,
        health_update_meta as do_update_meta,
        health_update_phases as do_update_phases,
        health_update_current_maxes as do_update_current_maxes,
        kg_to_lb,
        lb_to_kg,
        ipf_weight_classes,
        pct_of_max,
        calculate_attempts,
        days_until,
        health_new_version as do_new_version,
        import_parse_file,
        import_apply,
        import_reject,
        import_list_pending,
        import_get_pending,
        template_list,
        template_get,
        template_apply,
        template_apply_confirm,
        template_evaluate,
        template_create_from_block,
        template_copy,
        template_archive,
        template_unarchive,
        template_create_blank,
        template_create_from_payload,
        template_update,
        template_publish,
        template_unpublish,
        program_archive,
        program_unarchive,
        glossary_add,
        glossary_update,
        glossary_set_e1rm,
        glossary_generate_text,
        glossary_estimate_e1rm,
        glossary_estimate_fatigue,
        glossary_estimate_muscles,
    )

    ROUTES = {
        "health_get_program": lambda: health_get_program(),
        "health_setup_status": lambda: health_setup_status(),
        "health_setup_initialize": lambda: health_setup_initialize(
            args["mode"],
            args["start_date"],
            args["week_start_day"],
            args.get("program_name"),
            args.get("template_sk"),
            args.get("maxes"),
        ),
        "health_invalidate_program_cache": lambda: _do_health_invalidate_program_cache(args),
        "health_get_session": lambda: health_get_session(args["date"]),
        "health_update_session": lambda: do_update_session(args["date"], args["patch"]),
        "health_new_version": lambda: do_new_version(args["change_reason"], args["patches"]),
        "health_rag_search": lambda: health_rag_search(args["query"], args.get("n_results", 4)),
        "health_get_competition": lambda: health_get_competition(args["date"]),
        "health_get_diet_notes": lambda: health_get_diet_notes(args.get("start_date"), args.get("end_date")),
        "health_get_sessions_range": lambda: health_get_sessions_range(args["start_date"], args["end_date"]),
        "health_get_supplements": lambda: health_get_supplements(),
        "health_get_meta": lambda: health_get_meta(),
        "health_get_phases": lambda: health_get_phases(),
        "health_get_current_maxes": lambda: health_get_current_maxes(),
        "health_get_goals": lambda: health_get_goals(),
        "health_update_goals": lambda: do_update_goals(args["goals"]),
        "health_get_federation_library": lambda: health_get_federation_library(),
        "health_update_federation_library": lambda: do_update_federation_library({
            "federations": args["federations"],
            "qualification_standards": args["qualification_standards"],
        }),
        "health_update_competition": lambda: do_update_competition(args["date"], args["patch"]),
        "health_snapshot_competition_projection": lambda: do_snapshot_competition_projection(args["date"], args.get("version", "current"), args.get("allow_retrospective", False)),
        "health_complete_competition": lambda: do_complete_competition(args["date"], args["results"], args["body_weight_kg"], args.get("version", "current"), args.get("allow_retrospective", True), args.get("post_meet_report")),
        "health_update_diet_note": lambda: do_update_diet_note(args["date"], args["notes"]),
        "health_update_supplements": lambda: do_update_supplements(args["patch"]),
        "health_create_session": lambda: do_create_session(args["date"], args["day"], args["week_number"], args.get("exercises"), args.get("session_notes", "")),
        "health_delete_session": lambda: do_delete_session(args["date"]),
        "health_reschedule_session": lambda: do_reschedule_session(args["old_date"], args["new_date"]),
        "health_add_exercise": lambda: do_add_exercise(args["date"], args["exercise"]),
        "health_remove_exercise": lambda: do_remove_exercise(args["date"], args["exercise_index"]),
        "health_create_competition": lambda: do_create_competition(args["competition"]),
        "health_delete_competition": lambda: do_delete_competition(args["date"]),
        "health_delete_diet_note": lambda: do_delete_diet_note(args["date"]),
        "health_update_meta": lambda: do_update_meta(args["updates"]),
        "health_update_phases": lambda: do_update_phases(args["phases"]),
        "health_update_current_maxes": lambda: do_update_current_maxes(args.get("squat_kg"), args.get("bench_kg"), args.get("deadlift_kg")),
        "kg_to_lb": lambda: kg_to_lb(args["kg"]),
        "lb_to_kg": lambda: lb_to_kg(args["lb"]),
        "ipf_weight_classes": lambda: ipf_weight_classes(args["sex"]),
        "pct_of_max": lambda: pct_of_max(args["max_kg"], args["pct"]),
        "calculate_attempts": lambda: calculate_attempts(args["lift"], args["opener_kg"], args.get("j1_override"), args.get("j2_override"), args.get("last_felt")),
        "days_until": lambda: days_until(args["target_date"], args.get("label", "target")),
        "export_program_history": lambda: _do_export(args),
        "export_program_markdown": lambda: _do_export_program_markdown(args),
        "regenerate_analysis": lambda: _do_regenerate_analysis(args),
        "get_analysis_markdown": lambda: _do_get_analysis_markdown(args),
        "analyze_progression": lambda: _do_analyze_progression(args),
        "analyze_rpe_drift": lambda: _do_analyze_rpe_drift(args),
        "estimate_1rm": lambda: _do_estimate_1rm(args),
        "calculate_dots": lambda: _do_calculate_dots(args),
        "weekly_analysis": lambda: _do_weekly_analysis(args),
        "analysis_section": lambda: _do_analysis_section(args),
        "correlation_analysis": lambda: _do_correlation_analysis(args),
        "block_correlation_analysis": lambda: _do_block_correlation_analysis(args),
        "fatigue_profile_estimate": lambda: _do_fatigue_profile_estimate(args),
        "muscle_group_estimate": lambda: _do_muscle_group_estimate(args),
        "lift_profile_review": lambda: _do_lift_profile_review(args),
        "lift_profile_rewrite_and_estimate": lambda: _do_lift_profile_rewrite_and_estimate(args),
        "lift_profile_rewrite": lambda: _do_lift_profile_rewrite(args),
        "lift_profile_estimate_stimulus": lambda: _do_lift_profile_estimate_stimulus(args),
        "program_evaluation": lambda: _do_program_evaluation(args),
        "block_program_evaluation": lambda: _do_block_program_evaluation(args),
        "multi_block_comparison_analysis": lambda: _do_multi_block_comparison_analysis(args),
        "import_parse_file": lambda: import_parse_file(args["base64_content"], args["filename"]),
        "import_apply": lambda: import_apply(args["import_id"], args.get("merge_strategy", "append"), args.get("conflict_resolutions"), args.get("start_date"), args.get("actor_pk") or args.get("pk"), args.get("author")),
        "import_reject": lambda: import_reject(args["import_id"], args.get("reason")),
        "import_list_pending": lambda: import_list_pending(args.get("import_type")),
        "import_get_pending": lambda: import_get_pending(args["import_id"]),
        "template_list": lambda: template_list(args.get("include_archived", False), args.get("actor_pk") or args.get("pk")),
        "template_get": lambda: template_get(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_apply": lambda: template_apply(args["sk"], args.get("target", "new_block"), args.get("start_date"), args.get("week_start_day"), args.get("actor_pk") or args.get("pk")),
        "template_apply_confirm": lambda: template_apply_confirm(args["sk"], args.get("backfilled_maxes"), args.get("start_date"), args.get("week_start_day"), args.get("target", "new_block"), args.get("actor_pk") or args.get("pk")),
        "template_evaluate": lambda: template_evaluate(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_create_from_block": lambda: template_create_from_block(args["name"], args.get("program_sk"), args.get("actor_pk") or args.get("pk"), args.get("author")),
        "template_copy": lambda: template_copy(args["sk"], args["new_name"], args.get("actor_pk") or args.get("pk"), args.get("author")),
        "template_archive": lambda: template_archive(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_unarchive": lambda: template_unarchive(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_publish": lambda: template_publish(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_unpublish": lambda: template_unpublish(args["sk"], args.get("actor_pk") or args.get("pk")),
        "template_create_blank": lambda: template_create_blank(args["name"], args.get("description", ""), args.get("estimated_weeks", 4), args.get("days_per_week", 3), args.get("actor_pk") or args.get("pk"), args.get("author")),
        "template_create_from_payload": lambda: template_create_from_payload(args["template"], args.get("actor_pk") or args.get("pk"), args.get("author"), args.get("published", False), args.get("import_job_id")),
        "template_update": lambda: template_update(args["sk"], args["template"], args.get("actor_pk") or args.get("pk")),
        "program_archive": lambda: program_archive(args["sk"]),
        "program_unarchive": lambda: program_unarchive(args["sk"]),
        "glossary_add": lambda: glossary_add(args["exercise"]),
        "glossary_update": lambda: glossary_update(args["id"], args["fields"]),
        "glossary_set_e1rm": lambda: glossary_set_e1rm(args["id"], args["value_kg"], args.get("method", "manual")),
        "glossary_generate_text": lambda: glossary_generate_text(args["exercise"], args.get("lift_profiles")),
        "glossary_estimate_e1rm": lambda: glossary_estimate_e1rm(args["id"]),
        "glossary_estimate_fatigue": lambda: glossary_estimate_fatigue(args["id"]),
        "glossary_estimate_muscles": lambda: glossary_estimate_muscles(args["id"]),
        "powerlifting_filter_categories": lambda: asyncio.to_thread(_do_powerlifting_filter_categories, args),
        "analyze_powerlifting_stats": lambda: asyncio.to_thread(_do_analyze_powerlifting_stats, args),
        "powerlifting_ranking_percentile": lambda: asyncio.to_thread(_do_powerlifting_ranking_percentile, args),
    }

    handler = ROUTES.get(name)
    if not handler:
        return f"Unknown health tool: {name}"

    # If pk is supplied (e.g. from portal auth), override user-scoped health
    # stores. Templates are globally partitioned; pk is passed to template tools
    # above as actor identity instead of rewriting the template library PK.
    override_pk = args.get("pk")
    saved_pk = None
    if override_pk:
        from core import _get_store, _get_import_store, _get_glossary_store, _get_federation_store
        for getter in (_get_store, _get_import_store, _get_glossary_store, _get_federation_store):
            try:
                s = getter()
                if saved_pk is None:
                    saved_pk = s.pk
                s.pk = override_pk
            except Exception:
                pass

    try:
        result = handler()
        if asyncio.iscoroutine(result):
            result = await result
    finally:
        # Restore original pk to avoid leaking across calls
        if saved_pk is not None:
            for getter in (_get_store, _get_import_store, _get_glossary_store, _get_federation_store):
                try:
                    getter().pk = saved_pk
                except Exception:
                    pass

    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

# --- import_parse_file ---

class ImportParseFileAction(Action):
    base64_content: str = Field(description="Base64 encoded spreadsheet file content")
    filename: str = Field(description="Name of the file including extension")


class ImportParseFileObservation(Observation):
    pass


class ImportParseFileExecutor(ToolExecutor[ImportParseFileAction, ImportParseFileObservation]):
    def __call__(self, action: ImportParseFileAction, conversation=None) -> ImportParseFileObservation:
        from core import import_parse_file
        result = _run_async(import_parse_file(action.base64_content, action.filename))
        return ImportParseFileObservation.from_text(_format_result(result))


class ImportParseFileTool(ToolDefinition[ImportParseFileAction, ImportParseFileObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ImportParseFileTool"]:
        return [cls(
            description="Parse a spreadsheet file and stage it as a pending import. Returns import_id and classification.",
            action_type=ImportParseFileAction,
            observation_type=ImportParseFileObservation,
            executor=ImportParseFileExecutor(),
        )]


# --- import_apply ---

class ImportApplyAction(Action):
    import_id: str = Field(description="ID of the staged import to apply")
    merge_strategy: str = Field(default="append", description="Merge strategy: append, replace_planned, selective")
    conflict_resolutions: Optional[List[Dict[str, Any]]] = Field(default=None, description="Resolutions for session conflicts")
    start_date: Optional[str] = Field(default=None, description="Start date for templates (YYYY-MM-DD)")


class ImportApplyObservation(Observation):
    pass


class ImportApplyExecutor(ToolExecutor[ImportApplyAction, ImportApplyObservation]):
    def __call__(self, action: ImportApplyAction, conversation=None) -> ImportApplyObservation:
        from core import import_apply
        result = _run_async(import_apply(action.import_id, action.merge_strategy, action.conflict_resolutions, action.start_date))
        return ImportApplyObservation.from_text(_format_result(result))


class ImportApplyTool(ToolDefinition[ImportApplyAction, ImportApplyObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ImportApplyTool"]:
        return [cls(
            description="Apply a staged import to the program or template library.",
            action_type=ImportApplyAction,
            observation_type=ImportApplyObservation,
            executor=ImportApplyExecutor(),
        )]

# --- import_reject ---

class ImportRejectAction(Action):
    import_id: str = Field(description="ID of the staged import to reject")
    reason: Optional[str] = Field(default=None, description="Reason for rejection")


class ImportRejectObservation(Observation):
    pass


class ImportRejectExecutor(ToolExecutor[ImportRejectAction, ImportRejectObservation]):
    def __call__(self, action: ImportRejectAction, conversation=None) -> ImportRejectObservation:
        from core import import_reject
        result = _run_async(import_reject(action.import_id, action.reason))
        return ImportRejectObservation.from_text(_format_result(result))


class ImportRejectTool(ToolDefinition[ImportRejectAction, ImportRejectObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ImportRejectTool"]:
        return [cls(
            description="Reject a staged import, unblocking new imports of that type.",
            action_type=ImportRejectAction,
            observation_type=ImportRejectObservation,
            executor=ImportRejectExecutor(),
        )]

# --- import_list_pending ---

class ImportListPendingAction(Action):
    import_type: Optional[str] = Field(default=None, description="Filter by type: template, session_import")


class ImportListPendingObservation(Observation):
    pass


class ImportListPendingExecutor(ToolExecutor[ImportListPendingAction, ImportListPendingObservation]):
    def __call__(self, action: ImportListPendingAction, conversation=None) -> ImportListPendingObservation:
        from core import import_list_pending
        result = _run_async(import_list_pending(action.import_type))
        return ImportListPendingObservation.from_text(_format_result(result))


class ImportListPendingTool(ToolDefinition[ImportListPendingAction, ImportListPendingObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ImportListPendingTool"]:
        return [cls(
            description="List all awaiting_review imports.",
            action_type=ImportListPendingAction,
            observation_type=ImportListPendingObservation,
            executor=ImportListPendingExecutor(),
        )]

# --- import_get_pending ---

class ImportGetPendingAction(Action):
    import_id: str = Field(description="The import ID to fetch")


class ImportGetPendingObservation(Observation):
    pass


class ImportGetPendingExecutor(ToolExecutor[ImportGetPendingAction, ImportGetPendingObservation]):
    def __call__(self, action: ImportGetPendingAction, conversation=None) -> ImportGetPendingObservation:
        from core import import_get_pending
        result = _run_async(import_get_pending(action.import_id))
        return ImportGetPendingObservation.from_text(_format_result(result))


class ImportGetPendingTool(ToolDefinition[ImportGetPendingAction, ImportGetPendingObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ImportGetPendingTool"]:
        return [cls(
            description="Get a single pending import by ID.",
            action_type=ImportGetPendingAction,
            observation_type=ImportGetPendingObservation,
            executor=ImportGetPendingExecutor(),
        )]

# --- template_list ---

class TemplateListAction(Action):
    include_archived: bool = Field(default=False, description="Whether to include archived templates")


class TemplateListObservation(Observation):
    pass


class TemplateListExecutor(ToolExecutor[TemplateListAction, TemplateListObservation]):
    def __call__(self, action: TemplateListAction, conversation=None) -> TemplateListObservation:
        from core import template_list
        result = _run_async(template_list(action.include_archived))
        return TemplateListObservation.from_text(_format_result(result))


class TemplateListTool(ToolDefinition[TemplateListAction, TemplateListObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateListTool"]:
        return [cls(
            description="List all training templates in the library.",
            action_type=TemplateListAction,
            observation_type=TemplateListObservation,
            executor=TemplateListExecutor(),
        )]

# --- template_get ---

class TemplateGetAction(Action):
    sk: str = Field(description="SK of the template to retrieve (e.g. template#v001)")


class TemplateGetObservation(Observation):
    pass


class TemplateGetExecutor(ToolExecutor[TemplateGetAction, TemplateGetObservation]):
    def __call__(self, action: TemplateGetAction, conversation=None) -> TemplateGetObservation:
        from core import template_get
        result = _run_async(template_get(action.sk))
        return TemplateGetObservation.from_text(_format_result(result))


class TemplateGetTool(ToolDefinition[TemplateGetAction, TemplateGetObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateGetTool"]:
        return [cls(
            description="Get full training template structure.",
            action_type=TemplateGetAction,
            observation_type=TemplateGetObservation,
            executor=TemplateGetExecutor(),
        )]

# --- template_apply ---

class TemplateApplyAction(Action):
    sk: str = Field(description="SK of the template to apply")
    target: str = Field(default="new_block", description="Target: new_block, append, replace_planned")
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD)")
    week_start_day: str = Field(default="Monday", description="Week start day")


class TemplateApplyObservation(Observation):
    pass


class TemplateApplyExecutor(ToolExecutor[TemplateApplyAction, TemplateApplyObservation]):
    def __call__(self, action: TemplateApplyAction, conversation=None) -> TemplateApplyObservation:
        from core import template_apply
        result = _run_async(template_apply(action.sk, action.target, action.start_date, action.week_start_day))
        return TemplateApplyObservation.from_text(_format_result(result))


class TemplateApplyTool(ToolDefinition[TemplateApplyAction, TemplateApplyObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateApplyTool"]:
        return [cls(
            description="Apply a template to the program block. Runs Max Resolution Gate and returns preview.",
            action_type=TemplateApplyAction,
            observation_type=TemplateApplyObservation,
            executor=TemplateApplyExecutor(),
        )]

# --- template_apply_confirm ---

class TemplateApplyConfirmAction(Action):
    sk: str = Field(description="SK of the template to apply")
    backfilled_maxes: Optional[Dict[str, float]] = Field(default=None, description="Manual or AI backfilled maxes")
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD)")
    week_start_day: str = Field(default="Monday", description="Week start day")
    target: str = Field(default="new_block", description="Target: new_block, append, replace_planned")


class TemplateApplyConfirmObservation(Observation):
    pass


class TemplateApplyConfirmExecutor(ToolExecutor[TemplateApplyConfirmAction, TemplateApplyConfirmObservation]):
    def __call__(self, action: TemplateApplyConfirmAction, conversation=None) -> TemplateApplyConfirmObservation:
        from core import template_apply_confirm
        result = _run_async(template_apply_confirm(action.sk, action.backfilled_maxes, action.start_date, action.week_start_day, action.target))
        return TemplateApplyConfirmObservation.from_text(_format_result(result))


class TemplateApplyConfirmTool(ToolDefinition[TemplateApplyConfirmAction, TemplateApplyConfirmObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateApplyConfirmTool"]:
        return [cls(
            description="Confirm and write concretized block from template.",
            action_type=TemplateApplyConfirmAction,
            observation_type=TemplateApplyConfirmObservation,
            executor=TemplateApplyConfirmExecutor(),
        )]

# --- template_evaluate ---

class TemplateEvaluateAction(Action):
    sk: str = Field(description="SK of the template to evaluate")


class TemplateEvaluateObservation(Observation):
    pass


class TemplateEvaluateExecutor(ToolExecutor[TemplateEvaluateAction, TemplateEvaluateObservation]):
    def __call__(self, action: TemplateEvaluateAction, conversation=None) -> TemplateEvaluateObservation:
        from core import template_evaluate
        result = _run_async(template_evaluate(action.sk))
        return TemplateEvaluateObservation.from_text(_format_result(result))


class TemplateEvaluateTool(ToolDefinition[TemplateEvaluateAction, TemplateEvaluateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateEvaluateTool"]:
        return [cls(
            description="Run AI-powered template evaluation against athlete profile.",
            action_type=TemplateEvaluateAction,
            observation_type=TemplateEvaluateObservation,
            executor=TemplateEvaluateExecutor(),
        )]

# --- template_create_from_block ---

class TemplateCreateFromBlockAction(Action):
    name: str = Field(description="Name for the new template")
    program_sk: Optional[str] = Field(default=None, description="SK of source program version (defaults to current)")


class TemplateCreateFromBlockObservation(Observation):
    pass


class TemplateCreateFromBlockExecutor(ToolExecutor[TemplateCreateFromBlockAction, TemplateCreateFromBlockObservation]):
    def __call__(self, action: TemplateCreateFromBlockAction, conversation=None) -> TemplateCreateFromBlockObservation:
        from core import template_create_from_block
        result = _run_async(template_create_from_block(action.name, action.program_sk))
        return TemplateCreateFromBlockObservation.from_text(_format_result(result))


class TemplateCreateFromBlockTool(ToolDefinition[TemplateCreateFromBlockAction, TemplateCreateFromBlockObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateCreateFromBlockTool"]:
        return [cls(
            description="Convert current or specified program block into a reusable template.",
            action_type=TemplateCreateFromBlockAction,
            observation_type=TemplateCreateFromBlockObservation,
            executor=TemplateCreateFromBlockExecutor(),
        )]

# --- template_copy ---

class TemplateCopyAction(Action):
    sk: str = Field(description="SK of the template to copy")
    new_name: str = Field(description="Name for the new template")


class TemplateCopyObservation(Observation):
    pass


class TemplateCopyExecutor(ToolExecutor[TemplateCopyAction, TemplateCopyObservation]):
    def __call__(self, action: TemplateCopyAction, conversation=None) -> TemplateCopyObservation:
        from core import template_copy
        result = _run_async(template_copy(action.sk, action.new_name))
        return TemplateCopyObservation.from_text(_format_result(result))


class TemplateCopyTool(ToolDefinition[TemplateCopyAction, TemplateCopyObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateCopyTool"]:
        return [cls(
            description="Duplicate a training template.",
            action_type=TemplateCopyAction,
            observation_type=TemplateCopyObservation,
            executor=TemplateCopyExecutor(),
        )]

# --- template_archive ---

class TemplateArchiveAction(Action):
    sk: str = Field(description="SK of the template to archive")


class TemplateArchiveObservation(Observation):
    pass


class TemplateArchiveExecutor(ToolExecutor[TemplateArchiveAction, TemplateArchiveObservation]):
    def __call__(self, action: TemplateArchiveAction, conversation=None) -> TemplateArchiveObservation:
        from core import template_archive
        result = _run_async(template_archive(action.sk))
        return TemplateArchiveObservation.from_text(_format_result(result))


class TemplateArchiveTool(ToolDefinition[TemplateArchiveAction, TemplateArchiveObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateArchiveTool"]:
        return [cls(
            description="Archive a training template.",
            action_type=TemplateArchiveAction,
            observation_type=TemplateArchiveObservation,
            executor=TemplateArchiveExecutor(),
        )]

# --- template_unarchive ---

class TemplateUnarchiveAction(Action):
    sk: str = Field(description="SK of the template to unarchive")


class TemplateUnarchiveObservation(Observation):
    pass


class TemplateUnarchiveExecutor(ToolExecutor[TemplateUnarchiveAction, TemplateUnarchiveObservation]):
    def __call__(self, action: TemplateUnarchiveAction, conversation=None) -> TemplateUnarchiveObservation:
        from core import template_unarchive
        result = _run_async(template_unarchive(action.sk))
        return TemplateUnarchiveObservation.from_text(_format_result(result))


class TemplateUnarchiveTool(ToolDefinition[TemplateUnarchiveAction, TemplateUnarchiveObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateUnarchiveTool"]:
        return [cls(
            description="Unarchive a training template.",
            action_type=TemplateUnarchiveAction,
            observation_type=TemplateUnarchiveObservation,
            executor=TemplateUnarchiveExecutor(),
        )]

# --- template_create_blank ---

class TemplateCreateBlankAction(Action):
    name: str = Field(description="Name for the new template")
    description: str = Field(default="", description="Optional description")
    estimated_weeks: int = Field(default=4, description="Estimated program duration in weeks")
    days_per_week: int = Field(default=3, description="Training days per week")


class TemplateCreateBlankObservation(Observation):
    pass


class TemplateCreateBlankExecutor(ToolExecutor[TemplateCreateBlankAction, TemplateCreateBlankObservation]):
    def __call__(self, action: TemplateCreateBlankAction, conversation=None) -> TemplateCreateBlankObservation:
        from core import template_create_blank
        result = _run_async(template_create_blank(action.name, action.description, action.estimated_weeks, action.days_per_week))
        return TemplateCreateBlankObservation.from_text(_format_result(result))


class TemplateCreateBlankTool(ToolDefinition[TemplateCreateBlankAction, TemplateCreateBlankObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateCreateBlankTool"]:
        return [cls(
            description="Create a new blank training template with no sessions.",
            action_type=TemplateCreateBlankAction,
            observation_type=TemplateCreateBlankObservation,
            executor=TemplateCreateBlankExecutor(),
        )]


# --- template_update ---

class TemplateUpdateAction(Action):
    sk: str = Field(description="SK of the template to update (e.g. template#v001)")
    template: Dict = Field(description="Full template object to write back")


class TemplateUpdateObservation(Observation):
    pass


class TemplateUpdateExecutor(ToolExecutor[TemplateUpdateAction, TemplateUpdateObservation]):
    def __call__(self, action: TemplateUpdateAction, conversation=None) -> TemplateUpdateObservation:
        from core import template_update
        result = _run_async(template_update(action.sk, action.template))
        return TemplateUpdateObservation.from_text(_format_result(result))


class TemplateUpdateTool(ToolDefinition[TemplateUpdateAction, TemplateUpdateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["TemplateUpdateTool"]:
        return [cls(
            description="Overwrite an existing training template in place (metadata, phases, sessions).",
            action_type=TemplateUpdateAction,
            observation_type=TemplateUpdateObservation,
            executor=TemplateUpdateExecutor(),
        )]

# --- program_archive ---

class ProgramArchiveAction(Action):
    sk: str = Field(description="SK of the program version to archive")


class ProgramArchiveObservation(Observation):
    pass


class ProgramArchiveExecutor(ToolExecutor[ProgramArchiveAction, ProgramArchiveObservation]):
    def __call__(self, action: ProgramArchiveAction, conversation=None) -> ProgramArchiveObservation:
        from core import program_archive
        result = _run_async(program_archive(action.sk))
        return ProgramArchiveObservation.from_text(_format_result(result))


class ProgramArchiveTool(ToolDefinition[ProgramArchiveAction, ProgramArchiveObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ProgramArchiveTool"]:
        return [cls(
            description="Archive a program version. Repoints current if needed.",
            action_type=ProgramArchiveAction,
            observation_type=ProgramArchiveObservation,
            executor=ProgramArchiveExecutor(),
        )]

# --- program_unarchive ---

class ProgramUnarchiveAction(Action):
    sk: str = Field(description="SK of the program version to unarchive")


class ProgramUnarchiveObservation(Observation):
    pass


class ProgramUnarchiveExecutor(ToolExecutor[ProgramUnarchiveAction, ProgramUnarchiveObservation]):
    def __call__(self, action: ProgramUnarchiveAction, conversation=None) -> ProgramUnarchiveObservation:
        from core import program_unarchive
        result = _run_async(program_unarchive(action.sk))
        return ProgramUnarchiveObservation.from_text(_format_result(result))


class ProgramUnarchiveTool(ToolDefinition[ProgramUnarchiveAction, ProgramUnarchiveObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ProgramUnarchiveTool"]:
        return [cls(
            description="Unarchive a program version.",
            action_type=ProgramUnarchiveAction,
            observation_type=ProgramUnarchiveObservation,
            executor=ProgramUnarchiveExecutor(),
        )]

# --- glossary_add ---

class GlossaryAddAction(Action):
    exercise: Dict[str, Any] = Field(description="Exercise object with name, category, equipment")


class GlossaryAddObservation(Observation):
    pass


class GlossaryAddExecutor(ToolExecutor[GlossaryAddAction, GlossaryAddObservation]):
    def __call__(self, action: GlossaryAddAction, conversation=None) -> GlossaryAddObservation:
        from core import glossary_add
        result = _run_async(glossary_add(action.exercise))
        return GlossaryAddObservation.from_text(_format_result(result))


class GlossaryAddTool(ToolDefinition[GlossaryAddAction, GlossaryAddObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryAddTool"]:
        return [cls(
            description="Add a new exercise to the canonical glossary.",
            action_type=GlossaryAddAction,
            observation_type=GlossaryAddObservation,
            executor=GlossaryAddExecutor(),
        )]

# --- glossary_update ---

class GlossaryUpdateAction(Action):
    id: str = Field(description="ID of the exercise to update")
    fields: Dict[str, Any] = Field(description="Fields to update")


class GlossaryUpdateObservation(Observation):
    pass


class GlossaryUpdateExecutor(ToolExecutor[GlossaryUpdateAction, GlossaryUpdateObservation]):
    def __call__(self, action: GlossaryUpdateAction, conversation=None) -> GlossaryUpdateObservation:
        from core import glossary_update
        result = _run_async(glossary_update(action.id, action.fields))
        return GlossaryUpdateObservation.from_text(_format_result(result))


class GlossaryUpdateTool(ToolDefinition[GlossaryUpdateAction, GlossaryUpdateObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryUpdateTool"]:
        return [cls(
            description="Update exercise fields in the glossary.",
            action_type=GlossaryUpdateAction,
            observation_type=GlossaryUpdateObservation,
            executor=GlossaryUpdateExecutor(),
        )]

# --- glossary_set_e1rm ---

class GlossarySetE1rmAction(Action):
    id: str = Field(description="Exercise ID")
    value_kg: float = Field(description="e1RM estimate in kg")
    method: str = Field(default="manual", description="Method: manual, ai_backfill, logged")


class GlossarySetE1rmObservation(Observation):
    pass


class GlossarySetE1rmExecutor(ToolExecutor[GlossarySetE1rmAction, GlossarySetE1rmObservation]):
    def __call__(self, action: GlossarySetE1rmAction, conversation=None) -> GlossarySetE1rmObservation:
        from core import glossary_set_e1rm
        result = _run_async(glossary_set_e1rm(action.id, action.value_kg, action.method))
        return GlossarySetE1rmObservation.from_text(_format_result(result))


class GlossarySetE1rmTool(ToolDefinition[GlossarySetE1rmAction, GlossarySetE1rmObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossarySetE1rmTool"]:
        return [cls(
            description="Manually set an e1RM estimate for a glossary exercise.",
            action_type=GlossarySetE1rmAction,
            observation_type=GlossarySetE1rmObservation,
            executor=GlossarySetE1rmExecutor(),
        )]

# --- glossary_estimate_e1rm ---

class GlossaryEstimateE1rmAction(Action):
    id: str = Field(description="Exercise ID to estimate e1RM for")


class GlossaryEstimateE1rmObservation(Observation):
    pass


class GlossaryEstimateE1rmExecutor(ToolExecutor[GlossaryEstimateE1rmAction, GlossaryEstimateE1rmObservation]):
    def __call__(self, action: GlossaryEstimateE1rmAction, conversation=None) -> GlossaryEstimateE1rmObservation:
        from core import glossary_estimate_e1rm
        result = _run_async(glossary_estimate_e1rm(action.id))
        return GlossaryEstimateE1rmObservation.from_text(_format_result(result))


class GlossaryEstimateE1rmTool(ToolDefinition[GlossaryEstimateE1rmAction, GlossaryEstimateE1rmObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryEstimateE1rmTool"]:
        return [cls(
            description="AI backfill e1RM estimate for one exercise based on SBD maxes.",
            action_type=GlossaryEstimateE1rmAction,
            observation_type=GlossaryEstimateE1rmObservation,
            executor=GlossaryEstimateE1rmExecutor(),
        )]

# --- glossary_estimate_fatigue ---

class GlossaryEstimateFatigueAction(Action):
    id: str = Field(description="Exercise ID to estimate fatigue profile for")


class GlossaryEstimateFatigueObservation(Observation):
    pass


class GlossaryEstimateFatigueExecutor(ToolExecutor[GlossaryEstimateFatigueAction, GlossaryEstimateFatigueObservation]):
    def __call__(self, action: GlossaryEstimateFatigueAction, conversation=None) -> GlossaryEstimateFatigueObservation:
        from core import glossary_estimate_fatigue
        result = _run_async(glossary_estimate_fatigue(action.id))
        return GlossaryEstimateFatigueObservation.from_text(_format_result(result))


class GlossaryEstimateFatigueTool(ToolDefinition[GlossaryEstimateFatigueAction, GlossaryEstimateFatigueObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryEstimateFatigueTool"]:
        return [cls(
            description="AI fatigue profile estimation for one exercise.",
            action_type=GlossaryEstimateFatigueAction,
            observation_type=GlossaryEstimateFatigueObservation,
            executor=GlossaryEstimateFatigueExecutor(),
        )]


class GlossaryEstimateMusclesAction(Action):
    id: str = Field(description="Exercise ID to estimate muscle groups for")


class GlossaryEstimateMusclesObservation(Observation):
    pass


class GlossaryEstimateMusclesExecutor(ToolExecutor[GlossaryEstimateMusclesAction, GlossaryEstimateMusclesObservation]):
    def __call__(self, action: GlossaryEstimateMusclesAction, conversation=None) -> GlossaryEstimateMusclesObservation:
        from core import glossary_estimate_muscles
        result = _run_async(glossary_estimate_muscles(action.id))
        return GlossaryEstimateMusclesObservation.from_text(_format_result(result))


class GlossaryEstimateMusclesTool(ToolDefinition[GlossaryEstimateMusclesAction, GlossaryEstimateMusclesObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GlossaryEstimateMusclesTool"]:
        return [cls(
            description="AI muscle group estimation for one exercise.",
            action_type=GlossaryEstimateMusclesAction,
            observation_type=GlossaryEstimateMusclesObservation,
            executor=GlossaryEstimateMusclesExecutor(),
        )]


class HealthGetLifetimeComparisonAction(Action):
    block_keys: list[str] = Field(description="Keys of the blocks to compare.")


class HealthGetLifetimeComparisonObservation(Observation):
    pass


class HealthGetLifetimeComparisonExecutor(ToolExecutor[HealthGetLifetimeComparisonAction, HealthGetLifetimeComparisonObservation]):
    def __call__(self, action: HealthGetLifetimeComparisonAction, conversation=None) -> HealthGetLifetimeComparisonObservation:
        from core import health_get_lifetime_comparison
        result = _run_async(health_get_lifetime_comparison(action.block_keys))
        return HealthGetLifetimeComparisonObservation.from_text(_format_result(result))


class HealthGetLifetimeComparisonTool(ToolDefinition[HealthGetLifetimeComparisonAction, HealthGetLifetimeComparisonObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthGetLifetimeComparisonTool"]:
        return [cls(
            description=(
                "Generate a consolidated lifetime comparison report for multiple training blocks. "
                "Aggregates trends (SBD total, dots, volume, fatigue), exercise ROI signals, "
                "dose-response efficiency, and training patterns across the selected blocks. "
                "Requires cached analysis for each block."
            ),
            action_type=HealthGetLifetimeComparisonAction,
            observation_type=HealthGetLifetimeComparisonObservation,
            executor=HealthGetLifetimeComparisonExecutor(),
        )]


# --- health_suggest_e1rm_multipliers ---

class HealthSuggestE1rmMultipliersAction(Action):
    pass


class HealthSuggestE1rmMultipliersObservation(Observation):
    pass


class HealthSuggestE1rmMultipliersExecutor(ToolExecutor[HealthSuggestE1rmMultipliersAction, HealthSuggestE1rmMultipliersObservation]):
    def __call__(self, action: HealthSuggestE1rmMultipliersAction, conversation=None) -> HealthSuggestE1rmMultipliersObservation:
        from core import health_suggest_e1rm_multipliers
        result = _run_async(health_suggest_e1rm_multipliers())
        return HealthSuggestE1rmMultipliersObservation.from_text(_format_result(result))


class HealthSuggestE1rmMultipliersTool(ToolDefinition[HealthSuggestE1rmMultipliersAction, HealthSuggestE1rmMultipliersObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["HealthSuggestE1rmMultipliersTool"]:
        return [cls(
            description=(
                "Suggest per-lift e1RM manual correction multipliers based on known competition results "
                "and max history. Compares actual maxes against raw session-derived e1RM estimates near the same date. "
                "Returns suggestions for squat, bench, and deadlift if data is available."
            ),
            action_type=HealthSuggestE1rmMultipliersAction,
            observation_type=HealthSuggestE1rmMultipliersObservation,
            executor=HealthSuggestE1rmMultipliersExecutor(),
        )]


register_tool("HealthSuggestE1rmMultipliersTool", HealthSuggestE1rmMultipliersTool)
register_tool("HealthGetLifetimeComparisonTool", HealthGetLifetimeComparisonTool)
register_tool("GlossarySetE1rmTool", GlossarySetE1rmTool)
register_tool("GlossaryEstimateE1rmTool", GlossaryEstimateE1rmTool)
register_tool("GlossaryEstimateFatigueTool", GlossaryEstimateFatigueTool)
register_tool("GlossaryEstimateMusclesTool", GlossaryEstimateMusclesTool)
