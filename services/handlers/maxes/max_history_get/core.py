from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

import boto3
import hashlib
import json
from services.lib.competition_entries import load_entries
from services.competition_access import visible_entries

logger = logging.getLogger(__name__)

def _get_table():
    region = os.environ.get("AWS_REGION", "ca-central-1")
    table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    return boto3.resource("dynamodb", region_name=region).Table(table_name)


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _max_history_sk(version: str) -> str:
    return f"max_history#{version}"


def _scoped_entries(entries, access):
    if access.get('competition_scope', {}).get('read') is None:
        return entries
    unlinked = [entry for entry in entries if not entry.get('entry_id') and entry.get('context') != 'Competition result']
    linked = [entry for entry in entries if entry.get('entry_id')]
    visible = visible_entries(linked, access)
    for entry in linked:
        if entry in visible:
            continue
        identifier = str(entry['entry_id']).removeprefix('competition#').removeprefix('COMP#')
        if visible_entries([{**entry, 'master_id': identifier}], access):
            visible.append(entry)
    return [*unlinked, *visible]


async def max_history_get(args: dict) -> dict:
    """Get the max history for a program version.

    Args:
        args: dict with optional `pk` and `version` (defaults to "current").
    """
    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    if start_date:
        date.fromisoformat(str(start_date))
    if end_date:
        date.fromisoformat(str(end_date))
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    sk = _max_history_sk(version)
    resp = table.get_item(Key={"pk": pk, "sk": sk})
    item = resp.get("Item") or {
            "pk": pk,
            "sk": sk,
            "version": version,
            "entries": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    item = _sanitize_decimals(item)
    item["revision"] = int(item.get("revision", 0))
    history = {str(entry.get('entry_id')): entry for entry in item.get('entries', []) if entry.get('entry_id')}
    unkeyed = []
    for entry in item.get('entries', []):
        if entry.get('entry_id'):
            continue
        if not entry.get('id'):
            stable = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:24]
            entry["id"] = f"max-{stable}"
        unkeyed.append(entry)
    for competition in load_entries(pk):
        results = competition.get('results')
        if competition.get('user_status') != 'completed' or not isinstance(results, dict):
            continue
        master_id = competition.get('master_id') or str(competition.get('sk', '')).removeprefix('COMP#')
        identifier = f'competition#{master_id}'
        entry = {'entry_id': identifier, 'date': competition.get('start_date') or competition.get('date'), 'context': 'Competition result', 'bodyweight_kg': competition.get('body_weight_kg')}
        entry.update({lift: results.get(lift) for lift in ('squat_kg', 'bench_kg', 'deadlift_kg')})
        entry['total_kg'] = results.get('total_kg') or sum(value or 0 for lift, value in entry.items() if lift in ('squat_kg', 'bench_kg', 'deadlift_kg'))
        history[identifier] = entry
    entries = [*unkeyed, *history.values()]
    entries = _scoped_entries(entries, args.get('_access') or {})
    item['entries'] = sorted(entries, key=lambda entry: str(entry.get('date') or ''), reverse=True)
    if start_date or end_date:
        item["entries"] = [entry for entry in item.get("entries", []) if (not start_date or entry.get("date", "") >= start_date) and (not end_date or entry.get("date", "") <= end_date)]
    return _sanitize_decimals(item)
