from __future__ import annotations

import os
import re
from typing import Any

import boto3


def get_health_table():
    return boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(
        os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    )


def get_session_store(args: dict):
    from session_store import SessionStore

    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    return SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )


def get_s3():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ca-central-1"))


def video_extension(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", filename.rsplit(".", 1)[-1] if "." in filename else "mp4") or "mp4"


def resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def resolve_program_sk(health_table: Any, pk: str, version: str) -> str:
    if version == "current":
        pointer = health_table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def load_phases(health_table: Any, pk: str, program_sk: str):
    response = health_table.get_item(Key={"pk": pk, "sk": program_sk}, ProjectionExpression="phases")
    item = response.get("Item")
    return None if item is None else item.get("phases") or []


def context(health_table: Any, pk: str, version: str):
    program_sk = resolve_program_sk(health_table, pk, version)
    phases = load_phases(health_table, pk, program_sk)
    if phases is None:
        raise ValueError(f"Program version {version} not found")
    return program_sk, phases


def session_for_date(store: Any, program_sk: str, phases: list[dict], session_date: str):
    session = next((item for item in store.list_sessions_sync(program_sk, phases) if item.get("date") == session_date), None)
    if session is None:
        raise ValueError(f"Session with date {session_date} not found")
    return session


def strip_none(value):
    if isinstance(value, dict):
        return {key: strip_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [strip_none(item) for item in value]
    return value


def safe_number(value) -> float:
    return value if isinstance(value, (int, float)) and value == value else 0


def video_volume(item: dict) -> float:
    sets = safe_number(item.get("exercise_sets"))
    reps = safe_number(item.get("exercise_reps"))
    kg = safe_number(item.get("exercise_kg"))
    return sets * reps * kg if kg > 0 else sets * reps


def sort_items(items: list[dict], sort: str) -> list[dict]:
    if sort == "oldest":
        return sorted(items, key=lambda item: (str(item.get("session_date") or ""), str((item.get("video") or {}).get("uploaded_at") or "")))
    if sort == "volume":
        return sorted(items, key=lambda item: (video_volume(item), safe_number(item.get("exercise_kg")), str(item.get("session_date") or "")), reverse=True)
    if sort == "weight":
        return sorted(items, key=lambda item: (safe_number(item.get("exercise_kg")), str(item.get("session_date") or "")), reverse=True)
    return sorted(items, key=lambda item: (str(item.get("session_date") or ""), str((item.get("video") or {}).get("uploaded_at") or "")), reverse=True)
