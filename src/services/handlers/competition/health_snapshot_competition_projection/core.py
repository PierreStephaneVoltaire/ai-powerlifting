from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from services.lib.aws import dynamodb_resource
from services.lib.competition_entries import load_entries, with_competition_entries


def _health_table():
    return dynamodb_resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))


def _entries_table():
    return dynamodb_resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(os.environ.get("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"))


def _load_program(pk: str, version: str) -> dict:
    from services.lib.session_store import SessionStore
    table = _health_table()
    sk = (table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item") or {}).get("ref_sk") if version == "current" else f"program#{version}"
    item = table.get_item(Key={"pk": pk, "sk": sk}).get("Item") if sk else None
    if not item:
        raise ValueError(f"Program version {version} not found")
    program = {key: value for key, value in item.items() if key not in ("pk", "sk")}
    sessions = SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )
    program["sessions"] = sessions.list_sessions_sync(sk, program.get("phases") if isinstance(program.get("phases"), list) else [])
    return program


def _decimal(value):
    return None if value is None else Decimal(str(value))


def snapshot_entries(program: dict, entries: list[dict], snapshot_date, allow_retrospective: bool = False) -> list[dict]:
    from .analytics import meet_projection

    target = (snapshot_date + timedelta(days=7)).isoformat()
    updates = []
    for entry in entries:
        status = entry.get("user_status") or entry.get("status")
        if (entry.get("start_date") or entry.get("date")) != target or entry.get("projected_at_t_minus_1w") is not None:
            continue
        if status not in ("confirmed", "optional") and not (allow_retrospective and status == "completed"):
            continue
        projection = meet_projection(program, program.get("sessions", []), comp_date=target, ref_date=snapshot_date)
        if "total" not in projection:
            continue
        updates.append({
            "sk": entry["sk"],
            "name": entry.get("name"),
            "date": target,
            "projected_at_t_minus_1w": {
                "squat_kg": projection.get("squat"),
                "bench_kg": projection.get("bench"),
                "deadlift_kg": projection.get("deadlift"),
                "total_kg": projection.get("total"),
            },
            "projection_snapshot_date": snapshot_date.isoformat(),
        })
    return updates


async def health_snapshot_competition_projection(args: dict) -> dict:
    pk = args["pk"]
    snapshot_date = datetime.strptime(args["date"], "%Y-%m-%d").date()
    entries = load_entries(pk)
    program = with_competition_entries(_load_program(pk, args.get("version") or "current"), pk, entries)
    updates = snapshot_entries(program, entries, snapshot_date, bool(args.get("allow_retrospective")))
    table = _entries_table()
    now = datetime.now(timezone.utc).isoformat()
    for update in updates:
        table.update_item(
            Key={"pk": pk, "sk": update["sk"]},
            UpdateExpression="SET projected_at_t_minus_1w = :projection, projection_snapshot_date = :snapshot, updated_at = :now",
            ExpressionAttributeValues={
                ":projection": {key: _decimal(value) for key, value in update["projected_at_t_minus_1w"].items()},
                ":snapshot": update["projection_snapshot_date"],
                ":now": now,
            },
        )
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "updated": len(updates),
        "competitions": [{key: value for key, value in update.items() if key != "sk"} for update in updates],
    }
