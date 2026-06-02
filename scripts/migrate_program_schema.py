"""Migrate program schema to add planned/actual session model, fatigue categories, and current_maxes.

Reads the current program version from DynamoDB, applies additive schema changes,
writes as a new version, and updates the pointer. Idempotent -- safe to re-run.

Usage:
    python scripts/migrate_program_schema.py
    python scripts/migrate_program_schema.py --dry-run
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

POINTER_SK = "program#current"
PROGRAM_SK_PREFIX = "program#v"

PRIMARY_AXIAL_KEYWORDS = [
    "squat",
    "deadlift",
    "front squat",
    "rdl",
    "sumo",
]

PRIMARY_UPPER_KEYWORDS = [
    "bench",
    "ohp",
    "overhead press",
    "press",
]

SECONDARY_KEYWORDS = [
    "pause bench",
    "close grip",
    "block pull",
    "floor press",
    "incline bench",
    "spoto",
    "pin squat",
    "box squat",
    "tempo squat",
    "deficit deadlift",
    "paused deadlift",
]

def classify_fatigue_category(name: str) -> str:
    """Auto-classify an exercise's fatigue category by name matching.

    Order matters: secondary patterns are checked first (more specific),
    then primary patterns, then default to accessory.
    """
    lower = name.lower()

    for kw in SECONDARY_KEYWORDS:
        if kw in lower:
            return "secondary"

    for kw in PRIMARY_AXIAL_KEYWORDS:
        if kw in lower:
            return "primary_axial"

    for kw in PRIMARY_UPPER_KEYWORDS:
        if kw in lower:
            return "primary_upper"

    return "accessory"

def to_d(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_d(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_d(i) for i in obj]
    return obj

def generate_session_id(date: str, index: int) -> str:
    """Generate a stable UUID5 from session date and index."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"session:{date}:{index}"))

def load_program(table, pk: str) -> tuple[dict, int, str]:
    """Load the current program via pointer. Returns (program, version, ref_sk)."""
    pointer_resp = table.get_item(Key={"pk": pk, "sk": POINTER_SK})

    if "Item" not in pointer_resp:
        from boto3.dynamodb.conditions import Attr

        scan_result = table.scan(
            FilterExpression=Attr("pk").eq(pk) & Attr("sk").begins_with(PROGRAM_SK_PREFIX)
        )
        items = scan_result.get("Items", [])
        if not items:
            print("ERROR: No program found in table.", file=sys.stderr)
            sys.exit(1)

        latest_version = 0
        latest_sk = None
        for item in items:
            sk = item.get("sk", "")
            if sk.startswith(PROGRAM_SK_PREFIX):
                try:
                    v = int(sk[len(PROGRAM_SK_PREFIX) :])
                    if v > latest_version:
                        latest_version = v
                        latest_sk = sk
                except ValueError:
                    continue

        if not latest_sk:
            print("ERROR: No valid program versions found.", file=sys.stderr)
            sys.exit(1)

        version = latest_version
        ref_sk = latest_sk
    else:
        pointer = pointer_resp["Item"]
        ref_sk = pointer.get("ref_sk", "")
        if not ref_sk or not ref_sk.startswith(PROGRAM_SK_PREFIX):
            print(f"ERROR: Pointer has invalid ref_sk: {ref_sk!r}", file=sys.stderr)
            sys.exit(1)
        try:
            version = int(ref_sk[len(PROGRAM_SK_PREFIX):])
        except ValueError:
            print(f"ERROR: Cannot parse version from ref_sk: {ref_sk!r}", file=sys.stderr)
            sys.exit(1)

    program_resp = table.get_item(Key={"pk": pk, "sk": ref_sk})
    if "Item" not in program_resp:
        print(f"ERROR: Program item not found at {ref_sk}.", file=sys.stderr)
        sys.exit(1)

    program = dict(program_resp["Item"])
    program.pop("pk", None)
    program.pop("sk", None)

    return program, version, ref_sk

def migrate_sessions(sessions: list[dict]) -> tuple[list[dict], bool]:
    """Migrate session schema. Returns (sessions, changed_flag)."""
    changed = False

    for i, session in enumerate(sessions):
        if "id" not in session:
            date = session.get("date", "")
            session["id"] = generate_session_id(date, i)
            changed = True

        if "status" not in session:
            completed = session.get("completed", False)
            session["status"] = "completed" if completed else "planned"
            changed = True

        phase = session.get("phase")
        if isinstance(phase, dict):
            session["phase"] = phase.get("name", "")
            changed = True

        if "planned_exercises" not in session:
            session["planned_exercises"] = []
            changed = True

        for exercise in session.get("exercises", []):
            if "failed" not in exercise:
                exercise["failed"] = False
                changed = True

    return sessions, changed

def migrate_phases(phases: list[dict]) -> tuple[list[dict], bool]:
    """Add missing metadata fields to phases. Returns (phases, changed_flag)."""
    changed = False
    new_fields = {
        "target_rpe_min": None,
        "target_rpe_max": None,
        "days_per_week": None,
        "notes": None,
    }

    for phase in phases:
        for field, default in new_fields.items():
            if field not in phase:
                phase[field] = default
                changed = True

    return phases, changed

def migrate_glossary(program: dict, table, pk: str) -> tuple[list[dict], bool]:
    """Add fatigue_category to glossary exercises. Returns (exercises, changed_flag)."""
    glossary_sk = "glossary#v1"
    resp = table.get_item(Key={"pk": pk, "sk": glossary_sk})

    if "Item" not in resp:
        print("  No glossary found at glossary#v1 -- skipping glossary migration.")
        return [], False

    glossary = dict(resp["Item"])
    exercises = glossary.get("exercises", [])
    changed = False

    for exercise in exercises:
        if "fatigue_category" not in exercise:
            name = exercise.get("name", "")
            exercise["fatigue_category"] = classify_fatigue_category(name)
            changed = True

    if changed:
        glossary["updated_at"] = datetime.now(timezone.utc).isoformat()

    return exercises, changed

def populate_current_maxes(program: dict) -> tuple[dict, bool]:
    """Populate current_maxes from most recent competition results.

    Returns (maxes_dict, changed_flag).
    """
    existing = program.get("current_maxes", {})
    if existing:
        return existing, False

    competitions = program.get("competitions", [])

    sorted_comps = sorted(competitions, key=lambda c: c.get("date", ""), reverse=True)

    for comp in sorted_comps:
        results = comp.get("results", {})
        if results:
            maxes = {}
            if "squat_kg" in results:
                maxes["squat"] = float(results["squat_kg"])
            if "bench_kg" in results:
                maxes["bench"] = float(results["bench_kg"])
            if "deadlift_kg" in results:
                maxes["deadlift"] = float(results["deadlift_kg"])
            if maxes:
                return maxes, True

    last_comp = program.get("meta", {}).get("last_comp", {})
    results = last_comp.get("results", {})
    if results:
        maxes = {}
        if "squat_kg" in results:
            maxes["squat"] = float(results["squat_kg"])
        if "bench_kg" in results:
            maxes["bench"] = float(results["bench_kg"])
        if "deadlift_kg" in results:
            maxes["deadlift"] = float(results["deadlift_kg"])
        if maxes:
            return maxes, True

    return {}, False

def main():
    parser = argparse.ArgumentParser(description="Migrate program schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without writing to DynamoDB",
    )
    parser.add_argument("--table", default=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ca-central-1"))
    parser.add_argument("--pk", default=os.environ.get("IF_OPERATOR_PK", "operator"))
    args = parser.parse_args()

    print(f"[migrate] Table:  {args.table}")
    print(f"[migrate] Region: {args.region}")
    print(f"[migrate] PK:     {args.pk}")
    print(f"[migrate] Dry run: {args.dry_run}")
    print()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)

    print("[migrate] Loading current program...")
    program, version, ref_sk = load_program(table, args.pk)
    print(f"[migrate] Current version: {version} ({ref_sk})")
    print()

    new_program = copy.deepcopy(program)
    any_changed = False

    print("[migrate] Migrating sessions...")
    sessions = new_program.get("sessions", [])
    print(f"  {len(sessions)} sessions to process")
    sessions, sessions_changed = migrate_sessions(sessions)
    new_program["sessions"] = sessions
    if sessions_changed:
        print(f"  Sessions migrated")
    else:
        print(f"  Sessions already up to date")
    any_changed = any_changed or sessions_changed

    print("[migrate] Migrating phases...")
    phases = new_program.get("phases", [])
    print(f"  {len(phases)} phases to process")
    phases, phases_changed = migrate_phases(phases)
    new_program["phases"] = phases
    if phases_changed:
        print(f"  Phases migrated")
    else:
        print(f"  Phases already up to date")
    any_changed = any_changed or phases_changed

    print("[migrate] Migrating glossary exercises...")
    glossary_exercises, glossary_changed = migrate_glossary(new_program, table, args.pk)
    if glossary_exercises:
        print(f"  {len(glossary_exercises)} glossary exercises processed")
        cats = {}
        for ex in glossary_exercises:
            cat = ex.get("fatigue_category", "accessory")
            cats[cat] = cats.get(cat, 0) + 1
        print(f"  Fatigue categories: {cats}")
    if glossary_changed:
        print(f"  Glossary migrated")
    else:
        print(f"  Glossary already up to date")
    any_changed = any_changed or glossary_changed

    print("[migrate] Populating current_maxes...")
    maxes, maxes_changed = populate_current_maxes(new_program)
    if maxes_changed:
        new_program["current_maxes"] = maxes
        print(f"  Populated from competition results: {maxes}")
    elif maxes:
        print(f"  current_maxes already set: {maxes}")
    else:
        print(f"  No competition results found -- current_maxes not populated")
    any_changed = any_changed or maxes_changed

    print()

    if not any_changed:
        print("[migrate] No changes needed. Program already up to date.")
        return

    new_version = version + 1
    new_sk = f"{PROGRAM_SK_PREFIX}{new_version:03d}"
    now = datetime.now(timezone.utc).isoformat()

    if "meta" not in new_program:
        new_program["meta"] = {}
    new_program["meta"]["updated_at"] = now

    print(f"[migrate] New version: {new_version} ({new_sk})")

    if args.dry_run:
        print()
        print("[migrate] DRY RUN -- no changes written to DynamoDB.")
        print(f"  Would write program item: pk={args.pk!r}, sk={new_sk!r}")
        print(f"  Would update pointer: pk={args.pk!r}, sk={POINTER_SK!r}")
        if glossary_changed:
            print(f"  Would update glossary: pk={args.pk!r}, sk=glossary#v1")
        print()

        if sessions_changed and sessions:
            print("  Sample migrated session (first):")
            sample = {k: v for k, v in sessions[0].items() if k in ("id", "date", "status", "phase", "planned_exercises")}
            sample["exercises_count"] = len(sessions[0].get("exercises", []))
            sample["exercise_failed_fields"] = all(
                "failed" in ex for ex in sessions[0].get("exercises", [])
            )
            print(f"    {json.dumps(sample, indent=4, default=str)}")
        return

    print("[migrate] Writing new program version...")
    program_item = to_d({"pk": args.pk, "sk": new_sk, **new_program})
    table.put_item(Item=program_item)
    print(f"  Written: pk={args.pk!r}, sk={new_sk!r}")

    print("[migrate] Updating pointer...")
    pointer_item = to_d({
        "pk": args.pk,
        "sk": POINTER_SK,
        "version": new_version,
        "ref_sk": new_sk,
        "updated_at": now,
    })
    table.put_item(Item=pointer_item)
    print(f"  Pointer updated: version={new_version}")

    if glossary_changed and glossary_exercises:
        print("[migrate] Writing updated glossary...")
        glossary_item = to_d({
            "pk": args.pk,
            "sk": "glossary#v1",
            "exercises": glossary_exercises,
            "updated_at": now,
        })
        table.put_item(Item=glossary_item)
        print(f"  Glossary updated")

    print()
    print("[migrate] Migration complete.")
    print(f"  Program: v{version} -> v{new_version}")
    print(f"  Sessions migrated: {sum(1 for s in sessions if s.get('status'))}")
    print(f"  Phases enriched: {len(phases)}")
    if glossary_exercises:
        print(f"  Glossary exercises classified: {len(glossary_exercises)}")
    if maxes:
        print(f"  Current maxes: {maxes}")

if __name__ == "__main__":
    main()
