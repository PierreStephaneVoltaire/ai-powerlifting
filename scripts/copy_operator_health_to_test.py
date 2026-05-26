#!/usr/bin/env python3
"""Copy the current operator health program and sessions to pk=test.

This is meant for the private test environment. It copies:
  - if-health: pk=operator, sk=program#current pointer
  - if-health: the current program item pointed to by that pointer
  - if-sessions: all standalone session items for that program version
  - if-health-templates: pk=template_library global templates to pk=test
  - if-user: a deterministic test profile settings record mapped to pk=test

Every copied item is tagged with test_seed_marker so cleanup can remove the
seeded test data without guessing at keys.

Examples:
  python scripts/copy_operator_health_to_test.py --dry-run
  python scripts/copy_operator_health_to_test.py
  python scripts/copy_operator_health_to_test.py --replace
  python scripts/copy_operator_health_to_test.py --cleanup --dry-run
  python scripts/copy_operator_health_to_test.py --cleanup
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
TEMPLATE_SK_PREFIX = "template#"
DEFAULT_BLOCK = "current"
SEED_MARKER = "operator-health-current-to-test"


def to_dynamo(value: Any) -> Any:
    """Recursively convert Python floats for DynamoDB writes."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: to_dynamo(child) for key, child in value.items()}
    if isinstance(value, list):
        return [to_dynamo(child) for child in value]
    return value


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def version_number(program_sk: str) -> int | None:
    if not program_sk.startswith(PROGRAM_SK_PREFIX):
        return None
    try:
        return int(program_sk.removeprefix(PROGRAM_SK_PREFIX))
    except ValueError:
        return None


def version_label(program_sk: str) -> str:
    return program_sk.removeprefix("program#") if program_sk.startswith("program#") else program_sk


def session_prefix(program_sk: str) -> str:
    return f"{SESSION_SK_PREFIX}{program_sk}#"


def parse_week_number(session: dict[str, Any]) -> int:
    raw_week_number = session.get("week_number")
    parsed = int_value(raw_week_number, default=-1)
    if parsed >= 0:
        return parsed

    week = session.get("week")
    if isinstance(week, str):
        match = re.search(r"W(\d+)", week, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return int_value(week)


def phase_block(phase: dict[str, Any]) -> str:
    return str(phase.get("block") or DEFAULT_BLOCK)


def resolve_phase(session: dict[str, Any], phases: list[dict[str, Any]]) -> dict[str, Any]:
    week_number = parse_week_number(session)
    block = str(session.get("block") or DEFAULT_BLOCK)
    for phase in phases:
        if not isinstance(phase, dict) or phase_block(phase) != block:
            continue
        start_week = int_value(phase.get("start_week"))
        end_week = int_value(phase.get("end_week"))
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
    name = str(phase.get("name") or "Unscheduled").replace("#", "-")
    return f"phase#{block}#W{phase.get('start_week', 0)}-{phase.get('end_week', 0)}#{name}"


def seed_tags(source_pk: str, target_pk: str, copied_at: str, source_sk: str | None = None) -> dict[str, Any]:
    tags = {
        "test_seed_marker": SEED_MARKER,
        "test_seed_source_pk": source_pk,
        "test_seed_target_pk": target_pk,
        "test_seed_copied_at": copied_at,
    }
    if source_sk:
        tags["test_seed_source_sk"] = source_sk
    return tags


def query_by_prefix(table: Any, pk: str, sk_prefix: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def get_item(table: Any, pk: str, sk: str) -> dict[str, Any] | None:
    return table.get_item(Key={"pk": pk, "sk": sk}).get("Item")


def list_programs(table: Any, pk: str) -> list[dict[str, Any]]:
    programs = query_by_prefix(table, pk, PROGRAM_SK_PREFIX)
    return sorted(programs, key=lambda item: version_number(str(item.get("sk", ""))) or 0)


def resolve_current_program(table: Any, pk: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pointer = get_item(table, pk, POINTER_SK)
    if pointer:
        ref_sk = str(pointer.get("ref_sk") or "")
        if ref_sk:
            program = get_item(table, pk, ref_sk)
            if not program:
                raise RuntimeError(f"Pointer for pk={pk!r} references missing program {ref_sk!r}")
            return pointer, program

    programs = list_programs(table, pk)
    if not programs:
        raise RuntimeError(f"No program versions found for pk={pk!r}")

    program = programs[-1]
    program_sk = str(program["sk"])
    pointer = {
        "pk": pk,
        "sk": POINTER_SK,
        "version": version_number(program_sk) or 0,
        "ref_sk": program_sk,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return pointer, program


def sort_session_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            str(item.get("date") or ""),
            int_value(item.get("same_day_ordinal")),
            int_value(item.get("source_index")),
            str(item.get("sk") or ""),
        ),
    )


def list_session_items(table: Any, pk: str, program_sk: str) -> list[dict[str, Any]]:
    return sort_session_items(query_by_prefix(table, pk, session_prefix(program_sk)))


def stable_session_id(source_pk: str, program_sk: str, source_index: int, session: dict[str, Any]) -> str:
    existing = session.get("id") or session.get("session_id")
    if existing:
        return str(existing)
    seed = f"{source_pk}:{program_sk}:{source_index}:{session.get('date', '')}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def build_session_from_embedded(
    *,
    source_pk: str,
    target_pk: str,
    program_sk: str,
    session: dict[str, Any],
    source_index: int,
    same_day_ordinal: int,
    phases: list[dict[str, Any]],
    copied_at: str,
    source_table_name: str,
) -> dict[str, Any]:
    session_copy = copy.deepcopy(session)
    session_id = stable_session_id(source_pk, program_sk, source_index, session_copy)
    date_value = str(session_copy.get("date") or "undated")
    block = str(session_copy.get("block") or DEFAULT_BLOCK)
    status = str(session_copy.get("status") or ("completed" if session_copy.get("completed") else "planned"))
    completed = bool(session_copy.get("completed")) or status in {"logged", "completed"}
    phase = resolve_phase({**session_copy, "block": block}, phases)
    sk = f"{session_prefix(program_sk)}{date_value}#{same_day_ordinal:03d}#{session_id}"

    session_copy.update(
        {
            "id": session_id,
            "session_id": session_id,
            "date": date_value,
            "block": block,
            "status": status,
            "completed": completed,
            "week_number": parse_week_number(session_copy),
            "phase": phase,
            "phase_name": str(phase.get("name") or "Unscheduled"),
            "planned_exercises": session_copy.get("planned_exercises")
            if isinstance(session_copy.get("planned_exercises"), list)
            else [],
            "exercises": session_copy.get("exercises") if isinstance(session_copy.get("exercises"), list) else [],
        }
    )
    return {
        **session_copy,
        "pk": target_pk,
        "sk": sk,
        "entity_type": "session",
        "source_pk": target_pk,
        "source_table": source_table_name,
        "program_sk": program_sk,
        "program_version": version_label(program_sk),
        "program_version_number": version_number(program_sk),
        "source_index": source_index,
        "same_day_ordinal": same_day_ordinal,
        "phase_ref": phase_ref(phase),
        "updated_at": str(session_copy.get("updated_at") or copied_at),
        **seed_tags(source_pk, target_pk, copied_at, sk),
    }


def copy_program_item(program: dict[str, Any], source_pk: str, target_pk: str, copied_at: str) -> dict[str, Any]:
    item = copy.deepcopy(program)
    source_sk = str(item.get("sk") or "")
    item["pk"] = target_pk
    item.update(seed_tags(source_pk, target_pk, copied_at, source_sk))
    return item


def copy_pointer_item(pointer: dict[str, Any], source_pk: str, target_pk: str, copied_at: str) -> dict[str, Any]:
    item = copy.deepcopy(pointer)
    item["pk"] = target_pk
    item["sk"] = POINTER_SK
    item.update(seed_tags(source_pk, target_pk, copied_at, POINTER_SK))
    return item


def copy_session_item(item: dict[str, Any], source_pk: str, target_pk: str, copied_at: str) -> dict[str, Any]:
    copied = copy.deepcopy(item)
    source_sk = str(copied.get("sk") or "")
    copied["pk"] = target_pk
    copied["source_pk"] = target_pk
    copied.update(seed_tags(source_pk, target_pk, copied_at, source_sk))
    return copied


def copy_template_item(item: dict[str, Any], source_pk: str, target_pk: str, copied_at: str) -> dict[str, Any]:
    copied = copy.deepcopy(item)
    source_sk = str(copied.get("sk") or "")
    copied["pk"] = target_pk
    copied.update(seed_tags(source_pk, target_pk, copied_at, source_sk))
    return copied


def build_user_settings_item(args: argparse.Namespace, copied_at: str) -> dict[str, Any]:
    display_name = args.target_user_display_name or "Powerlifting Test"
    username = args.target_user_pk
    return {
        "pk": args.target_user_pk,
        "username": username,
        "discord_id": args.target_user_discord_id,
        "discord_username": username,
        "avatar_url": None,
        "nickname": args.target_user_nickname,
        "mapped_pk": args.target_pk,
        "profile_visibility": "public",
        "display_name": display_name,
        "bio": "Seeded profile settings for the private powerlifting test namespace.",
        "public_training_summary_enabled": True,
        "created_at": copied_at,
        "updated_at": copied_at,
        **seed_tags(args.source_user_pk, args.target_user_pk, copied_at, args.source_user_pk),
    }


def get_user_item(table: Any, pk: str) -> dict[str, Any] | None:
    return table.get_item(Key={"pk": pk}).get("Item")


def put_user_item(table: Any, item: dict[str, Any]) -> None:
    table.put_item(Item=to_dynamo(item))


def delete_user_items(table: Any, items: list[dict[str, Any]], dry_run: bool) -> int:
    if dry_run:
        return len(items)
    for item in items:
        table.delete_item(Key={"pk": item["pk"]})
    return len(items)


def existing_keys(table: Any, items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    conflicts: list[tuple[str, str]] = []
    for item in items:
        pk = str(item["pk"])
        sk = str(item["sk"])
        if get_item(table, pk, sk):
            conflicts.append((pk, sk))
    return conflicts


def put_items(table: Any, items: list[dict[str, Any]]) -> None:
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_dynamo(item))


def delete_items(table: Any, items: list[dict[str, Any]], dry_run: bool) -> int:
    if dry_run:
        return len(items)
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
    return len(items)


def is_seeded(item: dict[str, Any], source_pk: str, target_pk: str) -> bool:
    return (
        item.get("test_seed_marker") == SEED_MARKER
        and item.get("test_seed_source_pk") == source_pk
        and item.get("test_seed_target_pk") == target_pk
    )


def collect_cleanup_items(health_table: Any, sessions_table: Any, source_pk: str, target_pk: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    health_items = [
        item
        for item in query_by_prefix(health_table, target_pk, "program#")
        if is_seeded(item, source_pk, target_pk)
    ]
    session_items = [
        item
        for item in query_by_prefix(sessions_table, target_pk, SESSION_SK_PREFIX)
        if is_seeded(item, source_pk, target_pk)
    ]
    return health_items, session_items


def collect_template_cleanup_items(template_table: Any, source_pk: str, target_pk: str) -> list[dict[str, Any]]:
    return [
        item
        for item in query_by_prefix(template_table, target_pk, TEMPLATE_SK_PREFIX)
        if is_seeded(item, source_pk, target_pk)
    ]


def collect_user_cleanup_items(user_table: Any, source_pk: str, target_pk: str) -> list[dict[str, Any]]:
    item = get_user_item(user_table, target_pk)
    return [item] if item and is_seeded(item, source_pk, target_pk) else []


def copy_current(args: argparse.Namespace) -> int:
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    health_table = dynamodb.Table(args.health_table)
    sessions_table = dynamodb.Table(args.sessions_table)
    template_table = dynamodb.Table(args.templates_table)
    user_table = dynamodb.Table(args.user_table)
    copied_at = datetime.now(timezone.utc).isoformat()

    pointer, program = resolve_current_program(health_table, args.source_pk)
    program_sk = str(program["sk"])
    source_sessions = list_session_items(sessions_table, args.source_pk, program_sk)
    embedded_sessions = program.get("sessions") if isinstance(program.get("sessions"), list) else []

    if source_sessions:
        target_sessions = [
            copy_session_item(item, args.source_pk, args.target_pk, copied_at)
            for item in source_sessions
        ]
        session_source = "if-sessions"
    else:
        phases = program.get("phases") if isinstance(program.get("phases"), list) else []
        ordinals: defaultdict[str, int] = defaultdict(int)
        target_sessions = []
        for source_index, session in enumerate(embedded_sessions):
            if not isinstance(session, dict):
                continue
            date_value = str(session.get("date") or "undated")
            ordinals[date_value] += 1
            target_sessions.append(
                build_session_from_embedded(
                    source_pk=args.source_pk,
                    target_pk=args.target_pk,
                    program_sk=program_sk,
                    session=session,
                    source_index=source_index,
                    same_day_ordinal=ordinals[date_value],
                    phases=phases,
                    copied_at=copied_at,
                    source_table_name=args.health_table,
                )
            )
        session_source = "embedded program sessions"

    target_program = copy_program_item(program, args.source_pk, args.target_pk, copied_at)
    target_pointer = copy_pointer_item(pointer, args.source_pk, args.target_pk, copied_at)
    health_items = [target_program, target_pointer]
    target_templates: list[dict[str, Any]] = []
    existing_target_templates: list[dict[str, Any]] = []
    if not args.skip_templates:
        source_templates = query_by_prefix(template_table, args.source_template_library_pk, TEMPLATE_SK_PREFIX)
        target_templates = [
            copy_template_item(item, args.source_template_library_pk, args.target_template_library_pk, copied_at)
            for item in source_templates
        ]
        existing_target_templates = query_by_prefix(template_table, args.target_template_library_pk, TEMPLATE_SK_PREFIX)

    target_user_settings = None if args.skip_user_settings else build_user_settings_item(args, copied_at)
    existing_target_user = None if args.skip_user_settings else get_user_item(user_table, args.target_user_pk)

    existing_target_sessions = list_session_items(sessions_table, args.target_pk, program_sk)
    if not args.replace:
        conflicts = existing_keys(health_table, health_items)
        if existing_target_sessions:
            conflicts.extend((str(item["pk"]), str(item["sk"])) for item in existing_target_sessions[:10])
        if existing_target_templates:
            conflicts.extend((str(item["pk"]), str(item["sk"])) for item in existing_target_templates[:10])
        if existing_target_user:
            conflicts.append((str(existing_target_user["pk"]), "<user-settings>"))
        if conflicts:
            print("Refusing to copy because target items already exist. Re-run with --replace to overwrite pk=test.")
            for pk, sk in conflicts[:25]:
                print(f"  existing: pk={pk} sk={sk}")
            if len(conflicts) > 25:
                print(f"  ... {len(conflicts) - 25} more")
            return 2

    print("[operator-health-copy] Copy current operator program to test")
    print(f"  Health table:       {args.health_table}")
    print(f"  Sessions table:     {args.sessions_table}")
    print(f"  Templates table:    {args.templates_table}")
    print(f"  User table:         {args.user_table}")
    print(f"  Region:             {args.region}")
    print(f"  Source PK:          {args.source_pk}")
    print(f"  Target PK:          {args.target_pk}")
    print(f"  Source templates PK:{args.source_template_library_pk}")
    print(f"  Target templates PK:{args.target_template_library_pk}")
    print(f"  Program SK:         {program_sk}")
    print(f"  Source sessions:    {len(target_sessions)} ({session_source})")
    print(f"  Source templates:   {len(target_templates)}")
    print(f"  Existing target sessions for program: {len(existing_target_sessions)}")
    print(f"  Existing target templates: {len(existing_target_templates)}")
    print(f"  Target user settings: {'skipped' if args.skip_user_settings else args.target_user_pk}")
    print(f"  Replace:            {args.replace}")
    print(f"  Dry run:            {args.dry_run}")

    if target_sessions:
        date_counts = Counter(str(item.get("date") or "undated") for item in target_sessions)
        same_day_dates = sum(1 for count in date_counts.values() if count > 1)
        print(f"  Same-day dates:     {same_day_dates}")
        print("  Sample session SKs:")
        for item in target_sessions[: args.sample_keys]:
            print(f"    {item['sk']}")

    if args.dry_run:
        print("Dry run only; no DynamoDB writes performed.")
        return 0

    if args.replace and existing_target_sessions:
        deleted = delete_items(sessions_table, existing_target_sessions, dry_run=False)
        print(f"Deleted existing target sessions for {program_sk}: {deleted}")
    if args.replace and existing_target_templates:
        deleted = delete_items(template_table, existing_target_templates, dry_run=False)
        print(f"Deleted existing target templates: {deleted}")

    put_items(health_table, [target_program])
    put_items(sessions_table, target_sessions)
    put_items(template_table, target_templates)
    if target_user_settings:
        put_user_item(user_table, target_user_settings)
    put_items(health_table, [target_pointer])

    print("Copy complete.")
    print(f"  Wrote health items:   {len(health_items)}")
    print(f"  Wrote session items:  {len(target_sessions)}")
    print(f"  Wrote template items: {len(target_templates)}")
    print(f"  Wrote user settings:  {0 if args.skip_user_settings else 1}")
    print("Cleanup command:")
    print("  python scripts/copy_operator_health_to_test.py --cleanup")
    return 0


def cleanup(args: argparse.Namespace) -> int:
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    health_table = dynamodb.Table(args.health_table)
    sessions_table = dynamodb.Table(args.sessions_table)
    template_table = dynamodb.Table(args.templates_table)
    user_table = dynamodb.Table(args.user_table)
    health_items, session_items = collect_cleanup_items(
        health_table,
        sessions_table,
        args.source_pk,
        args.target_pk,
    )
    template_items = [] if args.skip_templates else collect_template_cleanup_items(
        template_table,
        args.source_template_library_pk,
        args.target_template_library_pk,
    )
    user_items = [] if args.skip_user_settings else collect_user_cleanup_items(
        user_table,
        args.source_user_pk,
        args.target_user_pk,
    )

    print("[operator-health-copy] Cleanup seeded test data")
    print(f"  Health table:    {args.health_table}")
    print(f"  Sessions table:  {args.sessions_table}")
    print(f"  Templates table: {args.templates_table}")
    print(f"  User table:      {args.user_table}")
    print(f"  Source PK:       {args.source_pk}")
    print(f"  Target PK:       {args.target_pk}")
    print(f"  Source templates PK: {args.source_template_library_pk}")
    print(f"  Target templates PK: {args.target_template_library_pk}")
    print(f"  Dry run:         {args.dry_run}")
    print(f"  Health items:    {len(health_items)}")
    print(f"  Session items:   {len(session_items)}")
    print(f"  Template items:  {len(template_items)}")
    print(f"  User items:      {len(user_items)}")

    if health_items:
        print("  Health item SKs:")
        for item in sorted(health_items, key=lambda row: str(row.get("sk") or ""))[: args.sample_keys]:
            print(f"    {item['sk']}")
    if session_items:
        print("  Sample session SKs:")
        for item in sort_session_items(session_items)[: args.sample_keys]:
            print(f"    {item['sk']}")
    if template_items:
        print("  Template item SKs:")
        for item in sorted(template_items, key=lambda row: str(row.get("sk") or ""))[: args.sample_keys]:
            print(f"    {item['sk']}")

    deleted_sessions = delete_items(sessions_table, session_items, args.dry_run)
    deleted_health = delete_items(health_table, health_items, args.dry_run)
    deleted_templates = delete_items(template_table, template_items, args.dry_run)
    deleted_users = delete_user_items(user_table, user_items, args.dry_run)

    if args.dry_run:
        print("Dry run only; no DynamoDB deletes performed.")
    else:
        print("Cleanup complete.")
    print(f"  {'Would delete' if args.dry_run else 'Deleted'} session items: {deleted_sessions}")
    print(f"  {'Would delete' if args.dry_run else 'Deleted'} health items:  {deleted_health}")
    print(f"  {'Would delete' if args.dry_run else 'Deleted'} template items:{deleted_templates}")
    print(f"  {'Would delete' if args.dry_run else 'Deleted'} user items:    {deleted_users}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the current operator health program and sessions to pk=test, or clean up copied test data.",
    )
    parser.add_argument("--health-table", default=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--sessions-table", default=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"))
    parser.add_argument("--templates-table", default=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"))
    parser.add_argument("--user-table", default=os.environ.get("IF_USER_TABLE", "if-user"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ca-central-1"))
    parser.add_argument("--source-pk", default=os.environ.get("HEALTH_PROGRAM_PK", "operator"))
    parser.add_argument("--target-pk", default=os.environ.get("POWERLIFTING_TEST_MAPPED_PK", "test"))
    parser.add_argument("--source-template-library-pk", default=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"))
    parser.add_argument("--target-template-library-pk", default=os.environ.get("IF_TEMPLATES_TEST_LIBRARY_PK", "test"))
    parser.add_argument("--source-user-pk", default=os.environ.get("POWERLIFTING_TEST_SOURCE_USER_PK", "operator"))
    parser.add_argument("--target-user-pk", default=os.environ.get("POWERLIFTING_TEST_USER_PK", "test"))
    parser.add_argument("--target-user-nickname", default=os.environ.get("POWERLIFTING_TEST_USER_NICKNAME", "test"))
    parser.add_argument("--target-user-display-name", default=os.environ.get("POWERLIFTING_TEST_USER_DISPLAY_NAME", "Powerlifting Test"))
    parser.add_argument("--target-user-discord-id", default=os.environ.get("POWERLIFTING_TEST_USER_DISCORD_ID", "test"))
    parser.add_argument("--skip-templates", action="store_true", help="Do not copy global template-library data")
    parser.add_argument("--skip-user-settings", action="store_true", help="Do not seed if-user profile settings for the test user")
    parser.add_argument("--replace", action="store_true", help="Overwrite the target current program and sessions")
    parser.add_argument("--cleanup", action="store_true", help="Delete items previously copied by this script")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing or deleting")
    parser.add_argument("--sample-keys", type=int, default=5, help="Number of sample keys to print")
    args = parser.parse_args()

    if args.source_pk == args.target_pk:
        print("ERROR: --source-pk and --target-pk must be different", file=sys.stderr)
        return 2

    try:
        return cleanup(args) if args.cleanup else copy_current(args)
    except ClientError as exc:
        message = exc.response.get("Error", {}).get("Message", str(exc))
        print(f"AWS ERROR: {message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
