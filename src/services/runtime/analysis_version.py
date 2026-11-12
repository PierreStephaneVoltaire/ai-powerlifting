from services.runtime import valkey

ANALYSIS_INPUT_WRITES = frozenset({
    "block_notes_update",
    "block_transition",
    "exercise_archive",
    "exercise_remove",
    "exercise_set_e1rm",
    "exercise_unarchive",
    "exercise_upsert",
    "federation_user_library_set",
    "glossary_estimate_e1rm",
    "glossary_estimate_fatigue",
    "glossary_estimate_muscles",
    "glossary_generate_text",
    "goals_replace",
    "health_complete_user_competition",
    "health_invalidate_program_cache",
    "health_new_version",
    "health_setup_initialize",
    "health_update_current_maxes",
    "health_update_user_competition",
    "import_apply",
    "max_history_add",
    "max_target_update",
    "program_archive",
    "program_unarchive",
    "program_update_lift_profiles",
    "program_update_meta_field",
    "program_update_phases",
    "session_create",
    "session_delete",
    "session_patch",
    "session_patch_by_date",
    "session_replace",
    "session_replace_all",
    "settings_update_age_class",
    "settings_update_athlete_basics",
    "settings_update_onboarding_profile",
    "settings_update_profile",
    "weight_log_add",
    "weight_log_remove",
})


def version_key(athlete: str) -> str:
    return f"pl:analysis-version:{athlete}"


def current(athlete: str) -> str:
    return valkey.get_text(version_key(athlete)) or "0"


def record_write(operation_name: str, athlete: str | None) -> None:
    if athlete and operation_name in ANALYSIS_INPUT_WRITES:
        valkey.increment(version_key(athlete))
