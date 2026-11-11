#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
OPERATIONS = ROOT / "src" / "services" / "operations"

WINDOWS = ["current", "previous_1", "previous_2", "previous_4", "previous_8", "block"]
FALLBACK_SECTIONS = ["overview", "workload", "fatigue_readiness", "peaking", "alerts"]
AI_SECTIONS = {"ai_correlation", "program_evaluation"}
RANKING_OPS = {"powerlifting_filter_categories", "powerlifting_ranking_percentile", "analyze_powerlifting_stats"}
LIFT_PATTERNS = {
    "squat": re.compile(r"^(competition )?(back )?squat$", re.I),
    "bench": re.compile(r"^(competition )?(flat )?bench( press)?$", re.I),
    "deadlift": re.compile(r"^(competition )?deadlift$", re.I),
}

RUNNER = r"""
import json, os, sys
import httpx
from services.principal import principal_token
token = os.environ["INTERNAL_API_TOKEN"]
for line in sys.stdin:
    request = json.loads(line)
    person, athlete, domain, name = request["person"], request["athlete"], request["domain"], request["name"]
    headers = {
        "X-Internal-Token": token,
        "X-Person-Pk": person,
        "X-Athlete-Pk": athlete,
        "X-PL-Principal": principal_token(person, athlete, name),
    }
    try:
        response = httpx.post(f"http://pl-{domain}:8000/operations/{name}", headers=headers, json=request["args"], timeout=request.get("timeout", 600))
        content_type = response.headers.get("content-type", "")
        body = response.json() if content_type.startswith("application/json") else response.text
        reply = {"status": response.status_code, "body": body}
    except Exception as exc:
        reply = {"status": 0, "body": {"error": str(exc)}}
    sys.stdout.write("\n@@RESULT@@" + json.dumps(reply, default=str) + "\n")
    sys.stdout.flush()
"""


class LiveServices:
    def __init__(self, namespace, deployment, person, athlete, split_domains):
        self.person = person
        self.athlete = athlete
        self.split_domains = split_domains
        self.domains = self._domain_map() if split_domains else None
        self.process = subprocess.Popen(
            ["kubectl", "-n", namespace, "exec", "-i", f"deploy/{deployment}", "--", "python", "-u", "-c", RUNNER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    @staticmethod
    def _domain_map():
        mapping = {}
        for path in OPERATIONS.glob("*.json"):
            for record in json.loads(path.read_text()):
                mapping[record["name"]] = record["domain"]
        return mapping

    def domain_for(self, name):
        if name in RANKING_OPS:
            return "rankings"
        if self.domains is not None:
            return self.domains[name]
        return "analytics"

    def call(self, name, args, timeout=600):
        payload = {"person": self.person, "athlete": self.athlete, "domain": self.domain_for(name), "name": name, "args": {"pk": self.athlete, **args}, "timeout": timeout}
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        for line in self.process.stdout:
            if line.startswith("@@RESULT@@"):
                return json.loads(line[len("@@RESULT@@"):])
        raise RuntimeError("kubectl exec runner exited; check kubectl context, namespace and deployment")

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        except Exception:
            self.process.kill()


def plain(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    if isinstance(value, set):
        return sorted(plain(item) for item in value)
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain(value), indent=2, sort_keys=True, default=str) + "\n")


def safe(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_")


def query_all(table, **kwargs):
    items = []
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last = response.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def snapshot_source(athlete, region, out):
    import boto3
    from boto3.dynamodb.conditions import Key

    resource = boto3.resource("dynamodb", region_name=region)
    health = resource.Table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    sessions_table = resource.Table(os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"))
    goals_table = resource.Table(os.environ.get("POWERLIFTING_GOALS_TABLE", "if-powerlifting-goals"))
    competitions_table = resource.Table(os.environ.get("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"))

    pointer = health.get_item(Key={"pk": athlete, "sk": "program#current"}).get("Item") or {}
    if not pointer.get("ref_sk"):
        raise SystemExit(f"No program#current pointer for {athlete}")
    program = health.get_item(Key={"pk": athlete, "sk": pointer["ref_sk"]}).get("Item") or {}
    weight_log = health.get_item(Key={"pk": athlete, "sk": "weight_log#current"}).get("Item") or {}
    glossary = health.get_item(Key={"pk": athlete, "sk": "glossary#v1"}).get("Item") or {}
    sessions = query_all(sessions_table, KeyConditionExpression=Key("pk").eq(athlete) & Key("sk").begins_with("session#"))
    goals = query_all(goals_table, KeyConditionExpression=Key("pk").eq(athlete) & Key("sk").begins_with("GOAL#"))
    competitions = query_all(competitions_table, IndexName="entries-by-date", KeyConditionExpression=Key("pk").eq(athlete))

    source = out / "source"
    write_json(source / "program_pointer.json", pointer)
    write_json(source / "program.json", program)
    write_json(source / "sessions.json", sessions)
    write_json(source / "weight_log.json", weight_log)
    write_json(source / "goals.json", goals)
    write_json(source / "glossary.json", glossary)
    write_json(source / "competitions.json", competitions)
    return plain(program), plain(sessions)


def find_first(value, keys):
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, "", {}):
                return value[key]
        for item in value.values():
            found = find_first(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_first(item, keys)
            if found is not None:
                return found
    return None


def main_lift_names(sessions):
    counts = {lift: {} for lift in LIFT_PATTERNS}
    for session in sessions:
        for exercise in session.get("exercises") or []:
            name = str(exercise.get("name") or "").strip()
            for lift, pattern in LIFT_PATTERNS.items():
                if pattern.match(name):
                    counts[lift][name] = counts[lift].get(name, 0) + 1
    names = {}
    for lift, found in counts.items():
        if found:
            names[lift] = max(found, key=found.get)
    return names


def athlete_inputs(program, args):
    meta = program.get("meta") or {}
    maxes = program.get("current_maxes") or meta.get("current_maxes") or meta.get("manual_maxes") or find_first(program, ["current_maxes", "manual_maxes"]) or {}

    def lift(*keys):
        for key in keys:
            value = maxes.get(key)
            if isinstance(value, dict):
                value = value.get("kg") or value.get("value") or value.get("e1rm")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return None

    sex = str(meta.get("sex") or find_first(program, ["sex"]) or "").strip().upper()[:1]
    bodyweight = meta.get("current_body_weight_kg") or find_first(program, ["current_body_weight_kg", "body_weight_kg", "bodyweight_kg"])
    inputs = {
        "squat_kg": args.squat or lift("squat", "squat_kg"),
        "bench_kg": args.bench or lift("bench", "bench_kg"),
        "deadlift_kg": args.deadlift or lift("deadlift", "dl", "deadlift_kg"),
        "bodyweight_kg": args.bodyweight or (float(bodyweight) if bodyweight else None),
        "sex_code": args.sex or (sex if sex in ("M", "F") else None),
    }
    return {key: value for key, value in inputs.items() if value is not None}


def extract_block_keys(listing):
    body = listing.get("body")
    blocks = body.get("blocks") if isinstance(body, dict) else body
    if isinstance(blocks, dict):
        blocks = blocks.get("blocks") or blocks.get("items")
    keys = []
    infos = []
    for block in blocks or []:
        if isinstance(block, str):
            key, info = block, {"key": block}
        else:
            key = block.get("blockKey") or block.get("key") or block.get("id")
            info = block
        if key:
            keys.append(str(key))
            infos.append(info)
    return keys, infos


def extract_section_keys(manifest):
    sections = (manifest.get("body") or {}).get("sections") or {}
    keys = [key for key in sections if key not in AI_SECTIONS]
    return keys or FALLBACK_SECTIONS


def is_ready(response):
    body = response.get("body")
    if response.get("status") != 200 or not isinstance(body, dict):
        return False
    payload = body.get("data") if isinstance(body.get("data"), dict) else body
    return str(payload.get("status") or "ready").lower() in ("ready", "complete", "completed", "succeeded", "fresh", "ok")



def main():
    parser = argparse.ArgumentParser(description="Read-only snapshot of the operator's source data and current deterministic analytics outputs into fixtures/operator.")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="asOfDate used for manifest and sections (default: today)")
    parser.add_argument("--athlete", default="operator")
    parser.add_argument("--person", default="operator")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ca-central-1"))
    parser.add_argument("--namespace", default="powerlifting")
    parser.add_argument("--deployment", default="pl-program", help="deployment whose pod runs the in-cluster request runner (needs httpx, services.principal, INTERNAL_API_TOKEN, PL_PRINCIPAL_SECRET)")
    parser.add_argument("--split-domains", action="store_true", help="route ops by the split operations/*.json domains instead of the legacy single analytics domain")
    parser.add_argument("--skip-source", action="store_true", help="skip DynamoDB source snapshot and reuse fixtures/operator/source")
    parser.add_argument("--skip-golden", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=90, help="bounded wait per section for sections_get to be ready")
    parser.add_argument("--squat", type=float)
    parser.add_argument("--bench", type=float)
    parser.add_argument("--deadlift", type=float)
    parser.add_argument("--bodyweight", type=float)
    parser.add_argument("--sex", choices=["M", "F"])
    parser.add_argument("--only", choices=["rankings"], help="re-call only this group and merge its entries into the existing golden manifest")
    parser.add_argument("--opl", action="store_true", help="download the OpenPowerlifting CSV from s3://$POWERLIFTING_S3_BUCKET/datasets/openpowerlifting-* into fixtures/opl/")
    args = parser.parse_args()

    out = FIXTURES / "operator"
    if not args.skip_source:
        program, sessions = snapshot_source(args.athlete, args.region, out)
        print(f"source snapshot written to {out / 'source'}")
    else:
        program = json.loads((out / "source" / "program.json").read_text())
        sessions = json.loads((out / "source" / "sessions.json").read_text())

    if args.opl:
        import boto3
        bucket = os.environ["POWERLIFTING_S3_BUCKET"]
        s3 = boto3.client("s3", region_name=args.region)
        target = FIXTURES / "opl"
        target.mkdir(parents=True, exist_ok=True)
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="datasets/openpowerlifting-"):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".csv"):
                    destination = target / Path(obj["Key"]).name
                    if not destination.exists() or destination.stat().st_size != obj["Size"]:
                        s3.download_file(bucket, obj["Key"], str(destination))
                        print(f"downloaded {destination}")

    if args.skip_golden:
        return

    golden = out / "golden"
    calls = []
    services = LiveServices(args.namespace, args.deployment, args.person, args.athlete, args.split_domains)

    def record(name, call_args, suffix=None):
        response = services.call(name, call_args)
        filename = safe(name) + (f"__{safe(suffix)}" if suffix else "")
        write_json(golden / f"{filename}.json", response)
        calls.append({"file": f"{filename}.json", "operation": name, "inputs": {"pk": args.athlete, **call_args}, "status": response["status"]})
        print(f"{response['status']} {filename}")
        return response

    block_keys, block_infos = [], []
    try:
        if args.only != "rankings":
            listing = record("analytics.blocks_list", {})
            block_keys, block_infos = extract_block_keys(listing)
            print(f"blocks: {block_keys}")

            for key in block_keys:
                record("analytics.blocks_get", {"blockKey": key, "cacheOnly": False, "refresh": False}, key)

            section_keys = None
            for window in WINDOWS:
                manifest = record("analytics.manifest", {"asOfDate": args.as_of, "window": window}, window)
                keys = extract_section_keys(manifest)
                section_keys = section_keys or keys
                record("analytics.sections_queue", {"asOfDate": args.as_of, "window": window, "sections": keys}, window)
                for key in keys:
                    deadline = time.time() + args.poll_seconds
                    while True:
                        response = services.call("analytics.sections_get", {"asOfDate": args.as_of, "window": window, "sectionKey": key})
                        if is_ready(response) or time.time() >= deadline:
                            break
                        time.sleep(3)
                    filename = f"analytics.sections_get__{safe(window)}__{safe(key)}"
                    write_json(golden / f"{filename}.json", response)
                    calls.append({"file": f"{filename}.json", "operation": "analytics.sections_get", "inputs": {"pk": args.athlete, "asOfDate": args.as_of, "window": window, "sectionKey": key}, "status": response["status"], "ready": is_ready(response)})
                    print(f"{response['status']} {filename}")

            for weeks in (1, 4):
                record("analytics.weekly", {"weeks": weeks, "block": "current", "refDate": args.as_of}, f"weeks{weeks}")

            lifts = main_lift_names(sessions)
            print(f"main lifts: {lifts}")
            for lift, name in lifts.items():
                record("analyze_progression", {"exercise_name": name, "window_weeks": 4}, lift)
                record("analyze_rpe_drift", {"exercise_name": name, "window_weeks": 4}, lift)

            if block_keys:
                record("analytics.compare", {"blockKeys": block_keys}, "all_blocks")

            past = next((key for key, info in zip(block_keys, block_infos) if key != "current" and str(info.get("status", "completed")).lower() not in ("active", "current")), None) or next((key for key in block_keys if key != "current"), None)
            if past:
                export = record("analytics.export", {"blockKey": past, "format": "markdown"}, past)
                body = export.get("body")
                if export["status"] == 200 and isinstance(body, dict) and body.get("content_base64"):
                    (golden / f"analytics.export__{safe(past)}.md").write_bytes(base64.b64decode(body["content_base64"]))

        inputs = athlete_inputs(program, args)
        print(f"ranking inputs: {inputs}")
        record("powerlifting_filter_categories", {})
        percentile_inputs = {key: value for key, value in inputs.items() if key in ("squat_kg", "bench_kg", "deadlift_kg", "bodyweight_kg", "sex_code")}
        if percentile_inputs:
            record("powerlifting_ranking_percentile", percentile_inputs)
        record("analyze_powerlifting_stats", percentile_inputs)
    finally:
        services.close()

    manifest_path = golden / "manifest.json"
    if args.only:
        existing = json.loads(manifest_path.read_text())
        replaced = {call["file"] for call in calls}
        existing["calls"] = [call for call in existing["calls"] if call["file"] not in replaced] + calls
        write_json(manifest_path, existing)
    else:
        write_json(manifest_path, {"asOfDate": args.as_of, "athlete": args.athlete, "blockKeys": block_keys, "calls": calls})
    print(f"golden written to {golden}")


if __name__ == "__main__":
    sys.exit(main())
