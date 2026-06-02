"""
IF Agent Regression Test Runner

Usage:
    python regression_runner.py              # API mode
    python regression_runner.py --discord    # Discord mode

Config (tests/.env):
    DISCORD_CHANNEL_ID=123456789012345678
    DISCORD_TEST_TOKEN=Bot MTxxxx...

Discord bot token for clears/reads is parsed from ../terraform/terraform.tfvars.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
TFVARS_PATH = REPO_ROOT / "terraform" / "terraform.tfvars"
PROMPTS_PATH = SCRIPT_DIR / "regression_prompts.yaml"
RESULTS_DIR = SCRIPT_DIR / "results"

API_URL = ""
MODEL = "if-prototype"
K8S_NAMESPACE = "if-portals"
K8S_DEPLOYMENT = "if-agent-api"

DISCORD_API = "https://discord.com/api/v10"

TIMEOUTS = {
    "general":       120,
    "health":        180,
    "coding_simple": 120,
    "coding_agentic": 360,
    "file_ops":      300,
    "skills":        180,
}

DISCORD_WAIT_PER_MESSAGE = 300
DISCORD_CLEAR_SETTLE     = 15

def load_env():
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

def parse_discord_bot_token():
    if not TFVARS_PATH.exists():
        sys.exit(f"ERROR: terraform.tfvars not found at {TFVARS_PATH}")
    text = TFVARS_PATH.read_text()
    match = re.search(r'discord_token\s*=\s*"([^"]+)"', text)
    if not match:
        sys.exit("ERROR: discord_token not found in terraform.tfvars")
    return match.group(1)

def load_prompts():
    data = yaml.safe_load(PROMPTS_PATH.read_text())
    return data["prompts"]

def make_results_dir():
    ts = time.strftime("%Y%m%d_%H%M")
    out = RESULTS_DIR / f"regression_{ts}"
    out.mkdir(parents=True, exist_ok=True)
    return out, ts

def kubectl(*args):
    result = subprocess.run(["kubectl", *args], capture_output=True, text=True)
    return result

def resolve_api_url():
    r = kubectl("get", "svc", "if-agent-api", "-n", K8S_NAMESPACE,
                "-o", "jsonpath={.spec.clusterIP}")
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"ERROR: could not resolve if-agent-api service IP:\n{r.stderr}")
    ip = r.stdout.strip()
    url = f"http://{ip}:8000"
    print(f"[config] API URL: {url}")
    return url

def rollout_and_wait():
    print(f"\n[rollout] Restarting {K8S_DEPLOYMENT} in {K8S_NAMESPACE}...")
    r = kubectl("rollout", "restart", f"deployment/{K8S_DEPLOYMENT}", "-n", K8S_NAMESPACE)
    if r.returncode != 0:
        sys.exit(f"ERROR: rollout restart failed:\n{r.stderr}")
    print(f"[rollout] {r.stdout.strip()}")

    print("[rollout] Waiting for rollout to complete (timeout 10m)...")
    r = kubectl("rollout", "status", f"deployment/{K8S_DEPLOYMENT}",
                "-n", K8S_NAMESPACE, "--timeout=10m")
    if r.returncode != 0:
        sys.exit(f"ERROR: rollout did not complete:\n{r.stderr}")
    print(f"[rollout] {r.stdout.strip()}")

    print("[rollout] Waiting for server to be ready...")
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            r = requests.get(f"{API_URL}/health", timeout=5)
            if r.status_code == 200:
                print("[rollout] Server is up.")
                return
        except Exception:
            pass
        time.sleep(5)
    sys.exit("ERROR: server did not become healthy within 5 minutes")

def download_pod_logs(out_dir: Path, ts: str):
    log_path = out_dir / f"pod_logs_{ts}.txt"
    print(f"\n[logs] Fetching pod logs...")
    r = kubectl("get", "pods", "-n", K8S_NAMESPACE,
                "-l", f"app={K8S_DEPLOYMENT}",
                "-o", "jsonpath={.items[0].metadata.name}")
    if r.returncode != 0 or not r.stdout.strip():
        print(f"WARNING: could not find pod name: {r.stderr}")
        return None
    pod_name = r.stdout.strip()
    r = kubectl("logs", pod_name, "-n", K8S_NAMESPACE, "--all-containers=true")
    if r.returncode != 0:
        print(f"WARNING: could not fetch logs: {r.stderr}")
        return None
    log_path.write_text(r.stdout)
    print(f"[logs] Saved to {log_path}")
    return log_path

def run_api_mode(prompts, out_dir: Path, ts: str):
    results_path = out_dir / f"api_responses_{ts}.txt"
    total = len(prompts)
    print(f"\n[api] Running {total} prompts against {API_URL}")

    with results_path.open("w") as f:
        for i, test in enumerate(prompts, 1):
            tid = test["id"]
            name = test["name"]
            category = test["category"]
            prompt = test["prompt"].strip()
            timeout = TIMEOUTS.get(category, 180)

            print(f"[api] ({i}/{total}) {tid} — {name} (timeout {timeout}s)...", end=" ", flush=True)

            start = time.time()
            try:
                resp = requests.post(
                    f"{API_URL}/v1/chat/completions",
                    json={
                        "model": MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "chat_id": f"regression_{tid}",
                        "stream": False,
                    },
                    timeout=timeout,
                )
                elapsed = round(time.time() - start, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    status = "OK"
                else:
                    content = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    status = "ERROR"
            except requests.Timeout:
                elapsed = round(time.time() - start, 1)
                content = f"TIMEOUT after {elapsed}s"
                status = "TIMEOUT"
            except Exception as e:
                elapsed = round(time.time() - start, 1)
                content = f"EXCEPTION: {e}"
                status = "ERROR"

            print(f"{status} ({elapsed}s)")

            f.write(f"{'=' * 60}\n")
            f.write(f"{tid} — {name}  [{status}]  ({elapsed}s)\n")
            f.write(f"CATEGORY: {category}\n")
            f.write(f"{'─' * 60}\n")
            f.write(f"PROMPT:\n{prompt}\n")
            f.write(f"{'─' * 60}\n")
            f.write(f"RESPONSE:\n{content}\n")
            f.write(f"\n")
            f.flush()

    print(f"\n[api] Results saved to {results_path}")
    return results_path

def discord_headers(token: str, bot: bool = True) -> dict:
    if bot and not token.startswith("Bot "):
        token = f"Bot {token}"
    return {"Authorization": token, "Content-Type": "application/json"}

def clear_discord_channel(channel_id: str, bot_token: str):
    headers = discord_headers(bot_token)
    deleted = 0

    while True:
        r = requests.get(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            params={"limit": 100},
            headers=headers,
        )
        if r.status_code != 200:
            print(f"  WARNING: could not fetch messages: {r.status_code} {r.text[:200]}")
            return
        messages = r.json()
        if not messages:
            break

        cutoff = time.time() - (14 * 86400)
        recent_ids = []
        old_ids = []
        for m in messages:
            snowflake = int(m["id"])
            created_ts = ((snowflake >> 22) / 1000) + 1420070400
            if created_ts > cutoff:
                recent_ids.append(m["id"])
            else:
                old_ids.append(m["id"])

        if len(recent_ids) >= 2:
            r2 = requests.post(
                f"{DISCORD_API}/channels/{channel_id}/messages/bulk-delete",
                headers=headers,
                json={"messages": recent_ids[:100]},
            )
            if r2.status_code not in (200, 204):
                print(f"  WARNING: bulk-delete failed: {r2.status_code} {r2.text[:200]}")
            else:
                deleted += len(recent_ids[:100])
        elif len(recent_ids) == 1:
            old_ids.extend(recent_ids)

        for mid in old_ids:
            requests.delete(
                f"{DISCORD_API}/channels/{channel_id}/messages/{mid}",
                headers=headers,
            )
            deleted += 1
            time.sleep(0.5)

        if len(messages) < 100:
            break

    print(f"  Cleared {deleted} messages.")

def send_discord_message(channel_id: str, send_token: str, content: str) -> str:
    r = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=discord_headers(send_token, bot=False),
        json={"content": content},
    )
    if r.status_code not in (200, 201):
        sys.exit(f"ERROR: send failed ({r.status_code}): {r.text[:300]}")
    return r.json()["id"]

def fetch_channel_history(channel_id: str, bot_token: str, after_id: str = None):
    params = {"limit": 50}
    if after_id:
        params["after"] = after_id
    r = requests.get(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=discord_headers(bot_token),
        params=params,
    )
    if r.status_code != 200:
        print(f"  WARNING: could not fetch history: {r.status_code} {r.text[:200]}")
        return []
    messages = r.json()
    return list(reversed(messages))

def run_discord_mode(prompts, out_dir: Path, ts: str):
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    send_token = os.environ.get("DISCORD_TEST_TOKEN", "").strip()

    if not channel_id:
        sys.exit("ERROR: DISCORD_CHANNEL_ID not set in tests/.env")
    if not send_token:
        sys.exit("ERROR: DISCORD_TEST_TOKEN not set in tests/.env")

    bot_token = parse_discord_bot_token()
    convo_path = out_dir / f"discord_convo_{ts}.txt"
    total = len(prompts)

    print(f"\n[discord] Running {total} prompts in channel {channel_id}")
    print(f"[discord] Using bot token for clears/reads, test token for sends")

    with convo_path.open("w") as f:
        for i, test in enumerate(prompts, 1):
            tid = test["id"]
            name = test["name"]
            category = test["category"]
            prompt = test["prompt"].strip()

            print(f"\n[discord] ({i}/{total}) {tid} — {name}")

            print(f"  Clearing channel...")
            clear_discord_channel(channel_id, bot_token)
            print(f"  Waiting {DISCORD_CLEAR_SETTLE}s after clear...")
            time.sleep(DISCORD_CLEAR_SETTLE)

            print(f"  Sending prompt...")
            sent_id = send_discord_message(channel_id, send_token, prompt)
            print(f"  Sent (id={sent_id}). Polling for response...")

            deadline = time.time() + DISCORD_WAIT_PER_MESSAGE
            history = []
            last_text_count = 0
            while time.time() < deadline:
                time.sleep(30)
                history = fetch_channel_history(channel_id, bot_token, after_id=sent_id)
                text_msgs = [m for m in history if m.get("content", "").strip()]
                if text_msgs and len(text_msgs) == last_text_count:
                    break
                if text_msgs:
                    last_text_count = len(text_msgs)
                    print(f"  {last_text_count} text message(s) so far, waiting for more...")
                elif history:
                    print(f"  {len(history)} embed(s) only, still waiting...")
            if last_text_count == 0:
                print(f"  TIMEOUT — no text response after {DISCORD_WAIT_PER_MESSAGE}s")

            f.write(f"{'=' * 60}\n")
            f.write(f"{tid} — {name}\n")
            f.write(f"CATEGORY: {category}\n")
            f.write(f"{'─' * 60}\n")
            f.write(f"PROMPT SENT:\n{prompt}\n")
            f.write(f"{'─' * 60}\n")
            f.write(f"CONVERSATION:\n")
            if history:
                for msg in history:
                    author = msg.get("author", {}).get("username", "unknown")
                    content = msg.get("content", "")
                    embeds = msg.get("embeds", [])
                    embed_text = ""
                    if embeds:
                        embed_summaries = [
                            e.get("title", "") + (" — " + e.get("description", "") if e.get("description") else "")
                            for e in embeds
                        ]
                        embed_text = f"  [embeds: {'; '.join(s for s in embed_summaries if s)}]"
                    f.write(f"[{author}] {content}{embed_text}\n")
            else:
                f.write("  (no messages captured)\n")
            f.write(f"\n")
            f.flush()
            print(f"  Captured {len(history)} messages.")

    print(f"\n[discord] Conversation saved to {convo_path}")
    return convo_path

def main():
    global API_URL
    load_env()

    parser = argparse.ArgumentParser(description="IF Agent Regression Runner")
    parser.add_argument("--discord", action="store_true", help="Run in Discord mode")
    args = parser.parse_args()

    API_URL = resolve_api_url()
    prompts = load_prompts()
    out_dir, ts = make_results_dir()

    rollout_and_wait()

    if args.discord:
        run_discord_mode(prompts, out_dir, ts)
    else:
        run_api_mode(prompts, out_dir, ts)

    download_pod_logs(out_dir, ts)

    print(f"\n[done] All output in {out_dir}")

if __name__ == "__main__":
    main()
