from __future__ import annotations

import asyncio
import base64
import binascii
import csv
import hashlib
import io
import json
import os
import re
from datetime import date, datetime

from .glossary import compatible_variation, create_missing_exercises

def _get_program_store(pk):
    from services.runtime.program_store import ProgramStore

    return ProgramStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk, os.getenv("AWS_REGION", "ca-central-1"))


def _get_glossary_store(pk):
    from services.runtime.glossary_store import GlossaryStore

    return GlossaryStore(pk=pk, region=os.getenv("AWS_REGION", "ca-central-1"))


def _get_import_store(pk):
    from .._import_store import ImportStore

    return ImportStore(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"), pk, os.getenv("AWS_REGION", "ca-central-1"))


def _file_hash(content):
    return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"


def _calendar_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            for date_format in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(value.strip(), date_format).date()
                except ValueError:
                    continue
            return None
    return None


def _week_from_sheet(sheet_name):
    match = re.search(r"\bweek\s*#?\s*(\d+)\b", sheet_name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _training_header(values):
    headers = {str(value).strip().casefold() for value in values if value is not None}
    has_day = bool(headers & {"day", "day of week", "weekday"})
    has_exercise = bool(headers & {"lift", "exercise", "exercise name", "movement"})
    return has_day and has_exercise


def _extract_xlsx(content, template=False):
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    rows = []
    sheet_headings = {}
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        if sheet.max_row is None or sheet.max_row < 2:
            continue
        sheet_rows = list(sheet.iter_rows(values_only=True))
        week_number = _week_from_sheet(sheet_name) if template else None
        header_index = 0
        if template:
            header_index = next((index for index, values in enumerate(sheet_rows[:12]) if _training_header(values)), 0)
            sheet_headings[sheet_name] = [
                value.strip()
                for values in sheet_rows[:header_index + 1]
                for value in values
                if isinstance(value, str) and value.strip()
            ]
        header_values = sheet_rows[header_index]
        dated_headers = {
            index: _calendar_date(value)
            for index, value in enumerate(header_values)
            if _calendar_date(value) is not None
        }
        event_columns = set()
        if template and dated_headers:
            label_column = next((index for index, value in enumerate(header_values) if str(value or "").strip().casefold() in {"date", "row_label"}), None)
            if label_column is not None:
                phase_row = next((values for values in sheet_rows[header_index + 1:] if str(values[label_column] or "").strip().casefold() in {"phase", "event", "type"}), None)
                if phase_row:
                    event_columns = {
                        index for index in dated_headers
                        if str(phase_row[index] or "").strip().casefold() in {"meet", "competition", "comp", "event"}
                    }
        relative_header_weeks = {
            index: (header_date - min(dated_headers.values())).days // 7 + 1
            for index, header_date in dated_headers.items()
            if index not in event_columns
        }
        headers = []
        for index, value in enumerate(header_values):
            if index in relative_header_weeks:
                headers.append(f"week_{relative_header_weeks[index]}")
            elif template and str(value or "").strip().casefold() == "date":
                headers.append("row_label")
            else:
                headers.append(str(value).strip() if value is not None else f"col_{index}")
        last_day = None
        for cells in sheet_rows[header_index + 1:]:
            row = {"_sheet": f"Week {week_number}" if week_number else sheet_name}
            if week_number:
                row["week_number"] = week_number
            has_data = False
            for index, cell in enumerate(cells):
                if index >= len(headers):
                    continue
                if index in event_columns:
                    continue
                value = cell
                if isinstance(value, (datetime, date)):
                    value = value.isoformat()
                if template and _calendar_date(value) and "date" in headers[index].casefold():
                    continue
                row[headers[index]] = value
                has_data |= value is not None
            if template and "day" in row:
                last_day = row["day"] or last_day
                row["day"] = last_day
            if has_data:
                rows.append(row)
    return rows, sheet_headings


def _extract_csv(content):
    return [row for row in csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace"))) if any(row.values())]


def _normalize_template_rows(rows):
    date_keys = {
        key for row in rows for key in row
        if "date" in key.casefold() and not any(token in key.casefold() for token in ("meet", "competition", "comp", "event"))
    }
    dates = [_calendar_date(row.get(key)) for row in rows for key in date_keys]
    dates = [value for value in dates if value]
    first_date = min(dates) if dates else None
    normalized = []
    for row in rows:
        output = {}
        for key, value in row.items():
            if key in date_keys:
                parsed_date = _calendar_date(value)
                if parsed_date and first_date:
                    output["_relative_week"] = (parsed_date - first_date).days // 7 + 1
                    output["_day_of_week"] = parsed_date.strftime("%A")
                elif key.casefold() == "date":
                    output["row_label"] = value
                continue
            normalized_key = key.casefold().replace("_", " ").replace("-", " ")
            if any(token in normalized_key for token in ("meet date", "competition date", "comp date", "event date")):
                continue
            if _calendar_date(value):
                continue
            if isinstance(value, str):
                value = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?\b", "", value)
            output[key] = value
        normalized.append(output)
    return normalized


def _exercise_key(name):
    return " ".join(str(name or "").casefold().split())


def _row_value(row, *names):
    wanted = {" ".join(name.casefold().replace("_", " ").replace("-", " ").split()) for name in names}
    return next((value for key, value in row.items()
                 if " ".join(str(key).casefold().replace("_", " ").replace("-", " ").split()) in wanted), None)


def _row_week(row):
    value = _row_value(row, "week_number", "week", "training week", "relative week", "_relative_week")
    if value is None:
        value = _week_from_sheet(str(_row_value(row, "_sheet") or ""))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _row_day(row):
    value = _row_value(row, "day_of_week", "day", "weekday", "_day_of_week")
    return " ".join(str(value).casefold().split()) if value is not None else None


def _source_exercise_notes(rows):
    from services.runtime.exercise_names import canonicalize_competition_lift

    notes = []
    for row in rows:
        name = _row_value(row, "exercise", "exercise name", "lift", "movement")
        note = _row_value(row, "exercise notes", "notes", "note")
        if not name or not note:
            continue
        canonical, _ = canonicalize_competition_lift(name)
        names = {_exercise_key(str(name)), _exercise_key(canonical)}
        notes.append({"names": names, "week": _row_week(row), "day": _row_day(row), "note": str(note)})
    return notes


def _normalize_exercise_names(parsed, source_notes):
    from services.runtime.exercise_names import canonicalize_competition_lift

    exercises = []
    for session in parsed.get("sessions", []):
        if not isinstance(session, dict):
            continue
        week, day = _row_week(session), _row_day(session)
        for exercise in session.get("exercises", []):
            if not isinstance(exercise, dict):
                continue
            name = str(exercise.get("name") or "").strip()
            canonical, _ = canonicalize_competition_lift(name)
            exercise["name"] = canonical
            exercise["notes"] = ""
            exercises.append((exercise, {_exercise_key(name), _exercise_key(canonical)}, week, day))

    matched = {}
    for source in source_notes:
        candidates = [i for i, (_, names, week, day) in enumerate(exercises)
                      if names & source["names"] and source["week"] in (None, week)
                      and source["day"] in (None, day)]
        if len(candidates) == 1:
            matched.setdefault(candidates[0], []).append(source["note"])
    for i, notes in matched.items():
        if len(notes) == 1:
            exercises[i][0]["notes"] = notes[0]


async def _dispatch(args):
    from .import_parse_ai import generate_import_parse_report

    try:
        content = base64.b64decode(args["base64_content"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64_content is invalid") from exc
    filename = args["filename"]
    classification = args["import_type"]
    if classification not in {"template", "session_import"}:
        raise ValueError("import_type must be template or session_import")
    if args.get("template_import") and classification != "template":
        raise ValueError("template_import requires import_type=template")
    is_template = classification == "template"
    rows, sheet_headings = _extract_xlsx(content, template=is_template) if filename.lower().endswith(".xlsx") else (_extract_csv(content), {})
    if is_template:
        rows = _normalize_template_rows(rows)
    pk = args["pk"]
    glossary = _get_glossary_store(pk)
    exercises = await glossary.get_glossary()
    if is_template:
        context = {"glossary": [{"id": item["id"], "name": item["name"]} for item in exercises if item.get("id") and item.get("name")]}
    else:
        try:
            program = await _get_program_store(pk).get_program()
            context = {
                "current_maxes": program.get("current_maxes", {}),
                "current_program_weeks": len({session.get("week_number") for session in program.get("sessions", []) if session.get("week_number")}),
            }
        except Exception:
            context = {"current_maxes": {}, "current_program_weeks": 0}
    parsed = await generate_import_parse_report(
        json.dumps(rows if is_template else rows[:100], indent=2, default=str),
        filename,
        classification,
        context,
        args.get("import_instructions", ""),
        sheet_headings,
    )
    if not isinstance(parsed, dict):
        raise ValueError("The AI parser returned an invalid result")
    errors = [warning for warning in parsed.get("warnings", []) if warning.get("type") == "error"]
    if errors:
        raise ValueError(errors[0].get("message") or "AI could not parse the uploaded file")
    if not parsed.get("sessions"):
        raise ValueError("No training sessions were found in the uploaded file")
    _normalize_exercise_names(parsed, _source_exercise_notes(rows))
    names = {
        exercise.get("name")
        for session in parsed.get("sessions", [])
        for exercise in session.get("exercises", [])
        if exercise.get("name")
    }
    resolved = {}
    for name in names:
        glossary_id = await glossary.fuzzy_resolve(name, threshold=0.92, exercises=exercises)
        if glossary_id:
            resolved[name] = glossary_id
    glossary_by_id = {str(item["id"]): item for item in exercises if item.get("id") and item.get("name")}
    glossary_by_name = {item["name"].casefold(): item for item in glossary_by_id.values()}
    for session in parsed.get("sessions", []):
        for exercise in session.get("exercises", []):
            name = str(exercise.get("name") or "").strip()
            suggested = exercise.pop("glossary_id", None)
            if not is_template:
                if name in resolved:
                    exercise["glossary_id"] = resolved[name]
                continue
            entry = glossary_by_name.get(name.casefold())
            if not entry:
                for candidate_id in (suggested, resolved.get(name)):
                    candidate = glossary_by_id.get(str(candidate_id))
                    if candidate and compatible_variation(name, candidate["name"]):
                        entry = candidate
                        break
            if entry:
                exercise["glossary_id"] = entry["id"]
                exercise["name"] = entry["name"]
    if args.get("template_import"):
        missing = {
            exercise["name"]
            for session in parsed.get("sessions", [])
            for exercise in session.get("exercises", [])
            if exercise.get("name") and not exercise.get("glossary_id")
        }
        if missing:
            current_exercises = await glossary.get_glossary()
            created = await asyncio.to_thread(create_missing_exercises, missing, parsed.get("new_exercises") or [], current_exercises, pk)
            for session in parsed.get("sessions", []):
                for exercise in session.get("exercises", []):
                    if exercise.get("name") in created and not exercise.get("glossary_id"):
                        exercise["glossary_id"] = created[exercise["name"]]
    import_id = await _get_import_store(pk).stage_import({
        "import_type": "template" if classification == "template" else "session_import",
        "source_filename": filename,
        "source_file_hash": _file_hash(content),
        "ai_parse_result": parsed,
    })
    result = {
        "import_id": import_id,
        "classification": classification,
        "warnings": parsed.get("warnings", []),
        "parse_notes": parsed.get("parse_notes", ""),
    }
    if args.get("template_import"):
        from ..import_apply.core import import_apply

        applied = await import_apply({
            "pk": pk,
            "import_id": import_id,
            "classification_override": "template",
            "_person_pk": args.get("actor_pk"),
            "author": args.get("author") or args.get("actor_pk"),
        })
        result["template_sk"] = applied["target_sk"]
    return result


def import_parse_file(args):
    return asyncio.run(_dispatch(args))
