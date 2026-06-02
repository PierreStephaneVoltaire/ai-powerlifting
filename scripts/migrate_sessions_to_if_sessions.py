"""Copy embedded health sessions into the if-sessions DynamoDB table.

This is intentionally additive. By default it reads the program version pointed
to by if-health program#current and writes one item per session into
if-sessions. It never deletes or edits the source program's embedded sessions
array.

Usage:
    python scripts/migrate_sessions_to_if_sessions.py --dry-run
    python scripts/migrate_sessions_to_if_sessions.py
    python scripts/migrate_sessions_to_if_sessions.py --version current
    python scripts/migrate_sessions_to_if_sessions.py --version program#v010 --replace
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

POINTER_SK = "program#current"
PROGRAM_SK_PREFIX = "program#v"
SESSION_SK_PREFIX = "session#"
DEFAULT_BLOCK = "current"

def to_dynamo(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB writes."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dynamo(v) for v in obj]
    return obj

def parse_week_number(session: dict[str, Any]) -> int:
    """Return the best available integer week number for a session."""
    raw_week_number = session.get("week_number")
    if isinstance(raw_week_number, int):
        return raw_week_number
    if isinstance(raw_week_number, Decimal):
        return int(raw_week_number)
    if isinstance(raw_week_number, str):
        try:
            return int(raw_week_number)
        except ValueError:
            pass

    week = session.get("week")
    if isinstance(week, int):
        return week
    if isinstance(week, Decimal):
        return int(week)
    if isinstance(week, str):
        match = re.search(r"W(\d+)", week, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        try:
            return int(week)
        except ValueError:
            pass

    return 0

def phase_block(phase: dict[str, Any]) -> str:
    return str(phase.get("block") or DEFAULT_BLOCK)

def resolve_phase(session: dict[str, Any], phases: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a full phase object for a session using block-scoped week ranges."""
    week_number = parse_week_number(session)
    block = str(session.get("block") or DEFAULT_BLOCK)

    for phase in phases:
        if phase_block(phase) != block:
            continue
        try:
            start_week = int(phase.get("start_week") or 0)
            end_week = int(phase.get("end_week") or 0)
        except (TypeError, ValueError):
            continue
        if start_week <= week_number <= end_week:
            return copy.deepcopy(phase)

    existing_phase = session.get("phase")
    if isinstance(existing_phase, dict) and existing_phase:
        phase = copy.deepcopy(existing_phase)
        phase.setdefault("block", block)
        return phase
    if isinstance(existing_phase, str) and existing_phase:
        return {
            "name": existing_phase,
            "intent": "",
            "start_week": week_number,
            "end_week": week_number,
            "block": block,
        }

    return {
        "name": "Unscheduled",
        "intent": "",
        "start_week": week_number,
        "end_week": week_number,
        "block": block,
    }

def phase_ref(phase: dict[str, Any]) -> str:
    block = str(phase.get("block") or DEFAULT_BLOCK)
    start_week = phase.get("start_week", 0)
    end_week = phase.get("end_week", 0)
    name = str(phase.get("name") or "Unscheduled").replace("#", "-")
    return f"phase#{block}#W{start_week}-W{end_week}#{name}"

def version_label(program_sk: str) -> str:
    if program_sk.startswith("program#"):
        return program_sk.removeprefix("program#")
    return program_sk

def version_number(program_sk: str) -> int | None:
    if not program_sk.startswith(PROGRAM_SK_PREFIX):
        return None
    try:
        return int(program_sk.removeprefix(PROGRAM_SK_PREFIX))
    except ValueError:
        return None

def normalize_version_arg(version: str) -> str:
    if version in {"all", "current"}:
        return version
    if version.startswith("program#v"):
        return version
    if version.startswith("v") and version[1:].isdigit():
        return f"program#{version}"
    raise ValueError("--version must be all, current, program#vNNN, or vNNN")

def stable_session_id(pk: str, program_sk: str, source_index: int, session: dict[str, Any]) -> str:
    existing = session.get("id")
    if existing:
        return str(existing)
    seed = f"{pk}:{program_sk}:{source_index}:{session.get('date', '')}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

def build_session_item(
    *,
    source_pk: str,
    source_table: str,
    program_sk: str,
    session: dict[str, Any],
    source_index: int,
    same_day_ordinal: int,
    phases: list[dict[str, Any]],
    migrated_at: str,
) -> dict[str, Any]:
    session_copy = copy.deepcopy(session)
    session_id = stable_session_id(source_pk, program_sk, source_index, session_copy)
    date_value = str(session_copy.get("date") or "undated")
    block = str(session_copy.get("block") or DEFAULT_BLOCK)
    completed = bool(session_copy.get("completed", False))
    status = str(session_copy.get("status") or ("completed" if completed else "planned"))
    week_number = parse_week_number(session_copy)
    phase = resolve_phase(session_copy, phases)
    phase_name = str(phase.get("name") or "Unscheduled")
    planned_exercises = session_copy.get("planned_exercises")
    if not isinstance(planned_exercises, list):
        planned_exercises = []

    session_copy["id"] = session_id
    session_copy["block"] = block
    session_copy["completed"] = completed
    session_copy["status"] = status
    session_copy["week_number"] = week_number
    session_copy["phase"] = phase
    session_copy["phase_name"] = phase_name
    session_copy["planned_exercises"] = planned_exercises

    session_sk = (
        f"{SESSION_SK_PREFIX}{program_sk}#"
        f"{date_value}#{same_day_ordinal:03d}#{session_id}"
    )

    item = {
        **session_copy,
        "pk": source_pk,
        "sk": session_sk,
        "entity_type": "session",
        "session_id": session_id,
        "source_pk": source_pk,
        "source_table": source_table,
        "program_sk": program_sk,
        "program_version": version_label(program_sk),
        "program_version_number": version_number(program_sk),
        "source_index": source_index,
        "same_day_ordinal": same_day_ordinal,
        "date": date_value,
        "phase": phase,
        "phase_name": phase_name,
        "phase_ref": phase_ref(phase),
        "migrated_at": migrated_at,
        "updated_at": str(session_copy.get("updated_at") or migrated_at),
    }
    return item

def query_all_programs(table: Any, pk: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs = {
        "KeyConditionExpression": (
            Key("pk").eq(pk) & Key("sk").begins_with(PROGRAM_SK_PREFIX)
        ),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return sorted(
        [item for item in items if str(item.get("sk", "")).startswith(PROGRAM_SK_PREFIX)],
        key=lambda item: version_number(str(item.get("sk", ""))) or 0,
    )

def load_program(table: Any, pk: str, sk: str) -> dict[str, Any]:
    response = table.get_item(Key={"pk": pk, "sk": sk})
    if "Item" not in response:
        raise RuntimeError(f"Program item not found: pk={pk!r}, sk={sk!r}")
    return response["Item"]

def resolve_current_program(table: Any, pk: str) -> dict[str, Any]:
    pointer_response = table.get_item(Key={"pk": pk, "sk": POINTER_SK})
    if "Item" in pointer_response:
        ref_sk = str(pointer_response["Item"].get("ref_sk") or "")
        if ref_sk:
            return load_program(table, pk, ref_sk)

    programs = query_all_programs(table, pk)
    if not programs:
        raise RuntimeError(f"No program versions found for pk={pk!r}")
    return programs[-1]

def selected_programs(table: Any, pk: str, version: str) -> list[dict[str, Any]]:
    normalized = normalize_version_arg(version)
    if normalized == "all":
        programs = query_all_programs(table, pk)
        if not programs:
            raise RuntimeError(f"No program versions found for pk={pk!r}")
        return programs
    if normalized == "current":
        return [resolve_current_program(table, pk)]
    return [load_program(table, pk, normalized)]

def put_session_item(table: Any, item: dict[str, Any], replace: bool) -> str:
    try:
        kwargs: dict[str, Any] = {"Item": to_dynamo(item)}
        if not replace:
            kwargs["ConditionExpression"] = (
                "attribute_not_exists(pk) AND attribute_not_exists(sk)"
            )
        table.put_item(**kwargs)
        return "copied"
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            return "skipped_existing"
        raise

def migrate(args: argparse.Namespace) -> int:
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    source_table = dynamodb.Table(args.source_table)
    target_table = dynamodb.Table(args.target_table)
    migrated_at = datetime.now(timezone.utc).isoformat()

    programs = selected_programs(source_table, args.pk, args.version)
    if not programs:
        print("No source programs selected.")
        return 0

    print(f"[sessions-migrate] Source table: {args.source_table}")
    print(f"[sessions-migrate] Target table: {args.target_table}")
    print(f"[sessions-migrate] Region:       {args.region}")
    print(f"[sessions-migrate] PK:           {args.pk}")
    print(f"[sessions-migrate] Version:      {args.version}")
    print(f"[sessions-migrate] Dry run:      {args.dry_run}")
    print(f"[sessions-migrate] Replace:      {args.replace}")
    print()

    copied = 0
    skipped_existing = 0
    total_sessions = 0
    source_planned_non_empty = 0
    source_planned_empty = 0
    same_day_extra_sessions = 0
    same_day_dates = 0
    sample_keys: list[str] = []
    warnings: list[str] = []

    for program in programs:
        program_sk = str(program.get("sk") or "")
        sessions = program.get("sessions") or []
        phases = program.get("phases") or []
        if not isinstance(sessions, list):
            warnings.append(f"{program_sk}: sessions is not a list; skipped")
            continue
        if not isinstance(phases, list):
            phases = []

        date_counts = Counter(
            str(session.get("date") or "undated")
            for session in sessions
            if isinstance(session, dict)
        )
        same_day_dates += sum(1 for count in date_counts.values() if count > 1)
        same_day_extra_sessions += sum(max(0, count - 1) for count in date_counts.values())

        ordinals: defaultdict[str, int] = defaultdict(int)
        program_copied = 0
        program_skipped = 0

        for source_index, session in enumerate(sessions):
            if not isinstance(session, dict):
                warnings.append(f"{program_sk}: sessions[{source_index}] is not an object; skipped")
                continue

            date_value = str(session.get("date") or "undated")
            if date_value == "undated":
                warnings.append(f"{program_sk}: sessions[{source_index}] has no date; copied as undated")

            ordinals[date_value] += 1
            item = build_session_item(
                source_pk=args.pk,
                source_table=args.source_table,
                program_sk=program_sk,
                session=session,
                source_index=source_index,
                same_day_ordinal=ordinals[date_value],
                phases=phases,
                migrated_at=migrated_at,
            )
            total_sessions += 1
            if item.get("planned_exercises"):
                source_planned_non_empty += 1
            else:
                source_planned_empty += 1

            if len(sample_keys) < args.sample_keys:
                sample_keys.append(item["sk"])

            if args.dry_run:
                program_copied += 1
                copied += 1
                continue

            result = put_session_item(target_table, item, args.replace)
            if result == "copied":
                program_copied += 1
                copied += 1
            else:
                program_skipped += 1
                skipped_existing += 1

        print(
            f"{program_sk}: source_sessions={len(sessions)} "
            f"copied={program_copied} skipped_existing={program_skipped}"
        )

    print()
    print("[sessions-migrate] Summary")
    print(f"  Source sessions selected:       {total_sessions}")
    print(f"  {'Would copy' if args.dry_run else 'Copied'}:                     {copied}")
    print(f"  Skipped existing:               {skipped_existing}")
    print(f"  Planned exercises non-empty:    {source_planned_non_empty}")
    print(f"  Planned exercises empty:        {source_planned_empty}")
    print(f"  Same-day dates encountered:     {same_day_dates}")
    print(f"  Extra same-day session ordinals: {same_day_extra_sessions}")

    if sample_keys:
        print("  Sample target SKs:")
        for key in sample_keys:
            print(f"    {key}")

    if warnings:
        print("  Warnings:")
        for warning in warnings:
            print(f"    {warning}")

    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Copy if-health sessions into if-sessions")
    parser.add_argument("--source-table", default=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--target-table", default=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ca-central-1"))
    parser.add_argument(
        "--pk",
        default=os.environ.get("HEALTH_PROGRAM_PK") or os.environ.get("IF_OPERATOR_PK") or "operator",
        help="Operator partition key to copy",
    )
    parser.add_argument(
        "--version",
        default="current",
        help="Program version to copy: all, current, program#vNNN, or vNNN",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build and report items without writing")
    parser.add_argument("--replace", action="store_true", help="Overwrite existing target session items")
    parser.add_argument("--sample-keys", type=int, default=5, help="Number of target SK samples to print")
    args = parser.parse_args()

    try:
        return migrate(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
