import base64
import json
import re
import time
from pathlib import Path

import httpx

from .seed import write_json

WINDOWS = ["current", "previous_1", "previous_2", "previous_4", "previous_8", "block"]
FALLBACK_SECTIONS = ["overview", "workload", "fatigue_readiness", "peaking", "alerts"]
AI_SECTIONS = {"ai_correlation", "program_evaluation"}
LIFT_PATTERNS = {
    "squat": re.compile(r"^(competition )?(back )?squat$", re.I),
    "bench": re.compile(r"^(competition )?(flat )?bench( press)?$", re.I),
    "deadlift": re.compile(r"^(competition )?deadlift$", re.I),
}
RANKING_INPUTS = {"squat_kg": 210, "bench_kg": 122.5, "deadlift_kg": 225, "bodyweight_kg": 78.018, "sex_code": "M"}


def safe(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_")


class Caller:
    def __init__(self, athlete, person, principal_token, internal_token, analytics_url, rankings_url):
        self.athlete = athlete
        self.person = person
        self.principal_token = principal_token
        self.internal_token = internal_token
        self.analytics_url = analytics_url
        self.rankings_url = rankings_url

    def call(self, name, args, rankings=False, timeout=900):
        headers = {
            "X-Internal-Token": self.internal_token,
            "X-Person-Pk": self.person,
            "X-Athlete-Pk": self.athlete,
            "X-PL-Principal": self.principal_token(self.person, self.athlete, name),
        }
        url = f"{self.rankings_url if rankings else self.analytics_url}/operations/{name}"
        try:
            response = httpx.post(url, headers=headers, json={"pk": self.athlete, **args}, timeout=timeout)
            content_type = response.headers.get("content-type", "")
            body = response.json() if content_type.startswith("application/json") else response.text
            return {"status": response.status_code, "body": body}
        except Exception as exc:
            return {"status": 0, "body": {"error": str(exc)}}


def main_lift_names(sessions):
    counts = {lift: {} for lift in LIFT_PATTERNS}
    for session in sessions:
        for exercise in session.get("exercises") or []:
            name = str(exercise.get("name") or "").strip()
            for lift, pattern in LIFT_PATTERNS.items():
                if pattern.match(name):
                    counts[lift][name] = counts[lift].get(name, 0) + 1
    return {lift: max(found, key=found.get) for lift, found in counts.items() if found}


def extract_block_keys(listing):
    body = listing.get("body")
    blocks = body.get("blocks") if isinstance(body, dict) else body
    if isinstance(blocks, dict):
        blocks = blocks.get("blocks") or blocks.get("items")
    keys, infos = [], []
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


class Recorder:
    def __init__(self, caller, golden_dir, athlete):
        self.caller = caller
        self.golden = Path(golden_dir)
        self.athlete = athlete
        self.calls = []

    def record(self, name, args, suffix=None, rankings=False):
        response = self.caller.call(name, args, rankings=rankings)
        filename = safe(name) + (f"__{safe(suffix)}" if suffix else "")
        write_json(self.golden / f"{filename}.json", response)
        self.calls.append({"file": f"{filename}.json", "operation": name, "inputs": {"pk": self.athlete, **args}, "status": response["status"]})
        print(f"{response['status']} {filename}", flush=True)
        return response

    def record_section(self, as_of, window, key, poll_seconds):
        deadline = time.time() + poll_seconds
        args = {"asOfDate": as_of, "window": window, "sectionKey": key}
        while True:
            response = self.caller.call("analytics.sections_get", args)
            if is_ready(response) or time.time() >= deadline:
                break
            time.sleep(3)
        filename = f"analytics.sections_get__{safe(window)}__{safe(key)}"
        write_json(self.golden / f"{filename}.json", response)
        self.calls.append({"file": f"{filename}.json", "operation": "analytics.sections_get", "inputs": {"pk": self.athlete, **args}, "status": response["status"], "ready": is_ready(response)})
        print(f"{response['status']} {filename}", flush=True)


def capture_analytics(recorder, as_of, sessions, poll_seconds):
    listing = recorder.record("analytics.blocks_list", {})
    block_keys, block_infos = extract_block_keys(listing)
    print(f"blocks: {block_keys}")
    for key in block_keys:
        recorder.record("analytics.blocks_get", {"blockKey": key, "cacheOnly": False, "refresh": False}, key)
    for window in WINDOWS:
        manifest = recorder.record("analytics.manifest", {"asOfDate": as_of, "window": window}, window)
        keys = extract_section_keys(manifest)
        recorder.record("analytics.sections_queue", {"asOfDate": as_of, "window": window, "sections": keys}, window)
        for key in keys:
            recorder.record_section(as_of, window, key, poll_seconds)
    for weeks in (1, 4):
        recorder.record("analytics.weekly", {"weeks": weeks, "block": "current", "refDate": as_of}, f"weeks{weeks}")
    lifts = main_lift_names(sessions)
    print(f"main lifts: {lifts}")
    for lift, name in lifts.items():
        recorder.record("analyze_progression", {"exercise_name": name, "window_weeks": 4}, lift)
        recorder.record("analyze_rpe_drift", {"exercise_name": name, "window_weeks": 4}, lift)
    if block_keys:
        recorder.record("analytics.compare", {"blockKeys": block_keys}, "all_blocks")
    past = next((key for key, info in zip(block_keys, block_infos) if key != "current" and str(info.get("status", "completed")).lower() not in ("active", "current")), None) or next((key for key in block_keys if key != "current"), None)
    if past:
        export = recorder.record("analytics.export", {"blockKey": past, "format": "markdown"}, past)
        body = export.get("body")
        if export["status"] == 200 and isinstance(body, dict) and body.get("content_base64"):
            (recorder.golden / f"analytics.export__{safe(past)}.md").write_bytes(base64.b64decode(body["content_base64"]))
    return block_keys


def wait_for_dataset(caller, timeout=1200):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = caller.call("powerlifting_filter_categories", {}, rankings=True)
        if response["status"] == 200 and isinstance(response["body"], dict):
            return
        time.sleep(5)
    raise SystemExit("rankings dataset never became ready")


def capture_rankings(recorder):
    wait_for_dataset(recorder.caller)
    recorder.record("powerlifting_filter_categories", {}, rankings=True)
    recorder.record("powerlifting_ranking_percentile", RANKING_INPUTS, rankings=True)
    recorder.record("analyze_powerlifting_stats", RANKING_INPUTS, rankings=True)


def write_manifest(golden_dir, as_of, athlete, block_keys, calls, merge=False):
    path = Path(golden_dir) / "manifest.json"
    if merge and path.is_file():
        existing = json.loads(path.read_text())
        replaced = {call["file"] for call in calls}
        calls = [call for call in existing["calls"] if call["file"] not in replaced] + calls
        block_keys = block_keys or existing.get("blockKeys", [])
    write_json(path, {"asOfDate": as_of, "athlete": athlete, "blockKeys": block_keys, "calls": calls})
