from __future__ import annotations

import asyncio
import copy
import os
import uuid
from datetime import date, datetime, timezone

from .._import_store import ImportStore


def _get_import_store(pk=None):
    return ImportStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk or os.getenv("HEALTH_PROGRAM_PK", "operator"), os.getenv("AWS_REGION", "ca-central-1"))


def _get_program_store(pk=None):
    from services.lib.program_store import ProgramStore

    return ProgramStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk or os.getenv("HEALTH_PROGRAM_PK", "operator"), os.getenv("AWS_REGION", "ca-central-1"))


def _get_template_store():
    from services.lib.template_store import TemplateStore

    return TemplateStore(
        os.getenv("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
        os.getenv("IF_TEMPLATES_LIBRARY_PK", "template_library"),
        os.getenv("AWS_REGION", "ca-central-1"),
    )


def _glossary(pk):
    from services.lib.glossary_store import GlossaryStore
    try:
        return GlossaryStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk=pk or "operator", region=os.getenv("AWS_REGION", "ca-central-1")).get_glossary_sync()
    except Exception:
        return []


def _days_per_week(sessions):
    weeks = {}
    for session in sessions:
        try:
            week = max(1, int(session.get("week_number") or 1))
        except (TypeError, ValueError):
            week = 1
        day = session.get("day_index") or session.get("day_of_week") or session.get("label") or "1"
        weeks.setdefault(week, set()).add(str(day))
    return max((len(days) for days in weeks.values()), default=0)


USER_SELECTED_RPE = 8


def _prepare_template(template, glossary=None):
    from services.lib.exercise_names import canonicalize_competition_lift, glossary_entry_for
    prepared = copy.deepcopy(template)
    metadata = prepared.setdefault("meta", {})
    sessions = prepared.setdefault("sessions", [])
    prepared.setdefault("phases", [])
    if not isinstance(sessions, list):
        sessions = prepared["sessions"] = []
    if not isinstance(prepared["phases"], list):
        prepared["phases"] = []
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    resolved, unresolved, required_maxes = set(), set(), set()
    max_week = 0
    for session in sessions:
        if not isinstance(session, dict):
            continue
        try:
            week = max(1, int(session.get("week_number") or 1))
        except (TypeError, ValueError):
            week = 1
        session["week_number"] = week
        session.pop("date", None)
        max_week = max(max_week, week)
        day = session.get("day_of_week")
        try:
            day_index = weekdays.index(day) + 1 if day in weekdays else int(session.get("day_index") or 1)
        except (TypeError, ValueError):
            day_index = 1
        day_index = max(1, min(7, day_index))
        session["day_index"] = day_index
        session.setdefault("day_of_week", weekdays[day_index - 1])
        session.setdefault("id", f"imported-{week}-{day_index}")
        session.setdefault("label", f"W{week}D{day_index}")
        exercises = session.get("exercises")
        if not isinstance(exercises, list):
            exercises = session["exercises"] = []
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            name = str(exercise.get("name") or "").strip()
            canonical, prescription = canonicalize_competition_lift(name)
            if canonical != name:
                exercise["name"] = canonical
            notes = str(exercise.get("notes") or "").strip()
            if prescription and prescription.casefold() not in notes.casefold():
                notes = f"{notes} {prescription}".strip()
            exercise["notes"] = notes
            exercise.setdefault("sets", None)
            exercise.setdefault("reps", None)
            load_type = str(exercise.get("load_type") or "unresolvable").lower()
            if load_type not in {"rpe", "percentage", "absolute", "unresolvable"}:
                load_type = "unresolvable"
            exercise["load_type"] = load_type
            if load_type == "percentage":
                try:
                    value = float(exercise.get("load_value"))
                    exercise["load_value"] = value / 100 if value > 1 else value
                except (TypeError, ValueError):
                    exercise["load_type"] = "unresolvable"
                    exercise["load_value"] = None
            if exercise["load_type"] == "unresolvable" or exercise.get("load_value") in (None, ""):
                exercise["load_type"] = "rpe"
                exercise["load_value"] = USER_SELECTED_RPE
                exercise["rpe_target"] = exercise.get("rpe_target") or USER_SELECTED_RPE
                note = f"Lifter selects the load at RPE {USER_SELECTED_RPE}."
                exercise["notes"] = f"{exercise['notes']} {note}".strip() if note not in str(exercise["notes"]) else exercise["notes"]
            load_type = exercise["load_type"]
            if glossary and canonical != name:
                entry = glossary_entry_for(exercise.get("name", ""), glossary)
                if entry and entry.get("id"):
                    exercise["glossary_id"] = entry["id"]
            elif not exercise.get("glossary_id") and glossary:
                entry = glossary_entry_for(exercise.get("name", ""), glossary)
                if entry and entry.get("id"):
                    exercise["glossary_id"] = entry["id"]
            glossary_id = exercise.get("glossary_id")
            if glossary_id:
                glossary_id = str(glossary_id)
                exercise["glossary_id"] = glossary_id
                resolved.add(glossary_id)
                if load_type in {"rpe", "percentage"}:
                    required_maxes.add(glossary_id)
            elif str(exercise.get("name") or "").strip():
                unresolved.add(str(exercise["name"]).strip())
    metadata.setdefault("name", "Imported Template")
    metadata.setdefault("description", "")
    metadata.setdefault("estimated_weeks", max_week)
    metadata.setdefault("days_per_week", _days_per_week(sessions))
    metadata.setdefault("archived", False)
    prepared["required_maxes"] = sorted(required_maxes)
    prepared["glossary_resolution"] = {
        "resolved": sorted(resolved),
        "unresolved": sorted(unresolved),
        "auto_added": [],
        "resolution_status": "partial" if resolved and unresolved else "unresolved" if unresolved else "resolved",
    }
    return prepared


def _shift_sessions(sessions, start_date):
    if not start_date or not sessions:
        return copy.deepcopy(sessions)
    target = date.fromisoformat(start_date)
    dates = [date.fromisoformat(session["date"]) for session in sessions if session.get("date")]
    if not dates:
        return copy.deepcopy(sessions)
    offset = target - min(dates)
    shifted = copy.deepcopy(sessions)
    for session in shifted:
        if session.get("date"):
            session["date"] = (date.fromisoformat(session["date"]) + offset).isoformat()
    return shifted


async def import_apply(args, merge_strategy="append", conflict_resolutions=None, start_date=None, actor_pk=None, author=None):
    if isinstance(args, str):
        args = {
            "pk": actor_pk or os.getenv("HEALTH_PROGRAM_PK", "operator"),
            "import_id": args,
            "merge_strategy": merge_strategy,
            "conflict_resolutions": conflict_resolutions,
            "start_date": start_date,
            "author": author,
        }
    pk = args["pk"]
    import_id = args["import_id"]
    import_store = _get_import_store(pk)
    pending = await import_store.get_pending(import_id)
    if not pending:
        raise ValueError(f"Import not found: {import_id}")
    if pending.get("status") != "awaiting_review":
        raise ValueError(f"Import {import_id} has already been {pending.get('status')}; do not replay this mutation")
    actor = args.get('_person_pk')
    if (args.get('classification_override') or pending.get('import_type')) == 'template' and not actor:
        raise ValueError('Verified acting Person required to author a Template')
    now = datetime.now(timezone.utc).isoformat()
    claim_id = uuid.uuid4().hex
    try:
        claimed = await import_store.claim_apply(import_id, claim_id, now)
    except Exception as exc:
        current = await import_store.get_pending(import_id)
        if current and current.get("status") != "awaiting_review":
            raise ValueError(f"Import {import_id} is {current.get('status')}; do not replay this mutation") from exc
        raise
    if claimed:
        pending = claimed
    try:
        parsed = copy.deepcopy(pending.get("ai_parse_result") or {})
        if args.get("glossary_overrides"):
            for session in parsed.get("sessions", []):
                for exercise in session.get("exercises", []):
                    glossary_id = args["glossary_overrides"].get(exercise.get("name"))
                    if glossary_id:
                        exercise["glossary_id"] = glossary_id
        import_type = args.get("classification_override") or pending.get("import_type")
        if import_type == "template":
            sessions = parsed.get("sessions") if isinstance(parsed.get("sessions"), list) else []
            template = _prepare_template({
                "meta": {
                    "name": "Imported Template",
                    "description": "",
                    "program_context": "",
                    "source_filename": pending.get("source_filename"),
                    "source_file_hash": pending.get("source_file_hash"),
                },
                "phases": parsed.get("phases", []),
                "sessions": sessions,
            }, glossary=await asyncio.to_thread(_glossary, pk))
            target_sk = await _get_template_store().put_template(
                template,
                actor_pk=actor,
                author=args.get("author") or actor,
                published=False,
                import_job_id=import_id,
            )
            await import_store.mark_applied(import_id, now, claim_id)
            return {"status": "applied", "target_sk": target_sk}

        staged = _shift_sessions(parsed.get("sessions", []), args.get("start_date"))
        if not staged:
            raise ValueError("No sessions found in staged import")
        program_store = _get_program_store(pk)
        program = copy.deepcopy(await program_store.get_program())
        existing = program.setdefault("sessions", [])
        by_date = {session.get("date"): session for session in existing if session.get("date")}
        resolutions = {item["session_date"]: item["action"] for item in args.get("conflict_resolutions", [])}
        applied = skipped = 0
        for session in staged:
            session_date = session.get("date")
            if not session_date:
                continue
            current = by_date.get(session_date)
            if current is None:
                existing.append(session)
                by_date[session_date] = session
                applied += 1
                continue
            strategy = args.get("merge_strategy", "append")
            action = resolutions.get(session_date, {"overwrite_future": "overwrite", "selective": "skip"}.get(strategy, strategy))
            if action == "skip":
                skipped += 1
            elif action in {"overwrite", "replace_planned"}:
                current.update(session)
                applied += 1
            elif action in {"merge", "append"}:
                current.setdefault("exercises", []).extend(session.get("exercises", []))
                current.setdefault("planned_exercises", []).extend(session.get("planned_exercises", []))
                applied += 1
        program["sessions"] = sorted(existing, key=lambda session: session.get("date", ""))
        written = await program_store._write_new_version(program, minor=False)
        await import_store.mark_applied(import_id, now, claim_id)
        return {
            "status": "applied",
            "applied_count": applied,
            "skipped_count": skipped,
            "new_version": (written or program).get("meta", {}).get("version_label"),
        }
    except Exception as exc:
        try:
            await import_store.mark_uncertain(import_id, claim_id, str(exc))
        except Exception:
            pass
        raise
