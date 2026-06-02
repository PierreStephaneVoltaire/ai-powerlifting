"""Live planner model-selection integration test for if-portals-test.

This test targets the private Kubernetes test namespace, not a local FastAPI
server. It verifies that the deployed API reads the mounted test MODELS_PATH,
uses the cheap test allowlist, and writes a plan whose selected_model matches
that allowlist.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

NAMESPACE = os.getenv("IF_TEST_NAMESPACE", "if-portals-test")
SERVICE = os.getenv("IF_TEST_API_SERVICE", "if-agent-api")
MODEL = os.getenv("IF_TEST_MODEL", "deepseek/deepseek-v4-flash")
LOCAL_PORT = int(os.getenv("IF_TEST_API_PORT", "8001"))
API_URL_ENV = os.getenv("IF_TEST_API_URL", "").rstrip("/")
KUBECTL = os.getenv("KUBECTL", "kubectl")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("IF_TEST_REQUEST_TIMEOUT_SECONDS", "240"))

@dataclass
class CommandResult:
    stdout: str
    stderr: str

def run_kubectl(*args: str, check: bool = True) -> CommandResult:
    result = subprocess.run(
        [KUBECTL, *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"kubectl {' '.join(args)} failed with {result.returncode}:\n{result.stderr.strip()}"
        )
    return CommandResult(result.stdout, result.stderr)

def wait_for_http(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {url}: {last_error}")

def start_port_forward() -> tuple[subprocess.Popen[str] | None, str]:
    if API_URL_ENV:
        wait_for_http(f"{API_URL_ENV}/health")
        return None, API_URL_ENV

    proc = subprocess.Popen(
        [
            KUBECTL,
            "-n",
            NAMESPACE,
            "port-forward",
            f"svc/{SERVICE}",
            f"{LOCAL_PORT}:8000",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    api_url = f"http://127.0.0.1:{LOCAL_PORT}"
    try:
        wait_for_http(f"{api_url}/health")
    except Exception:
        proc.terminate()
        try:
            _, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        raise RuntimeError(f"port-forward failed before API became healthy:\n{stderr.strip()}")
    return proc, api_url

def post_chat(api_url: str, chat_id: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Planner integration check. Reply with one short sentence and do not call tools."
                ),
            }
        ],
        "chat_id": chat_id,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{api_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"chat completion failed with HTTP {exc.code}:\n{body}") from exc

def get_api_pod() -> str:
    result = run_kubectl(
        "-n",
        NAMESPACE,
        "get",
        "pods",
        "-l",
        f"app={SERVICE}",
        "-o",
        "json",
    )
    pod_list = json.loads(result.stdout)
    for pod in pod_list.get("items", []):
        status = pod.get("status", {})
        conditions = status.get("conditions", [])
        if status.get("phase") != "Running":
            continue
        if any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions):
            return pod["metadata"]["name"]
    raise RuntimeError(f"No ready pod found for app={SERVICE} in namespace {NAMESPACE}")

def exec_in_pod(pod: str, command: str) -> str:
    return run_kubectl("-n", NAMESPACE, "exec", pod, "--", "sh", "-lc", command).stdout

def selected_model_from_plan(plan_text: str) -> str:
    match = re.search(r"(?m)^selected_model:\s*['\"]?([^'\"\n]+)['\"]?\s*$", plan_text)
    if not match:
        raise AssertionError(f"plan.md did not contain selected_model:\n{plan_text}")
    return match.group(1).strip()

def main() -> int:
    print(f"[config] namespace={NAMESPACE} service={SERVICE} model={MODEL}")
    run_kubectl("-n", NAMESPACE, "rollout", "status", f"deployment/{SERVICE}", "--timeout=300s")

    port_forward, api_url = start_port_forward()
    chat_id = f"planner-model-selection-{uuid.uuid4().hex[:8]}"
    pod = get_api_pod()

    try:
        print(f"[api] POST {api_url}/v1/chat/completions chat_id={chat_id}")
        response = post_chat(api_url, chat_id)
        content = response["choices"][0]["message"]["content"]
        if "planner failed" in content.lower():
            raise AssertionError(f"planner failure returned to user:\n{content}")

        models_path = exec_in_pod(
            pod,
            'printf "%s" "${MODELS_PATH:-/app/models}"',
        ).strip()
        model_ids_raw = exec_in_pod(pod, f"cat {shlex.quote(models_path)}/model_ids.txt")
        model_ids = [
            line.strip()
            for line in model_ids_raw.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if model_ids != [MODEL]:
            raise AssertionError(f"test model allowlist should contain only {MODEL}, got {model_ids}")

        rules = exec_in_pod(pod, f"cat {shlex.quote(models_path)}/model_selection_rules.md")
        if "Test Model Selection Rules" not in rules or MODEL not in rules:
            raise AssertionError(
                f"mounted model_selection_rules.md does not look like the test policy:\n{rules}"
            )
        if "anthropic/" in rules or "openai/" in rules or "perplexity/" in rules:
            raise AssertionError("test model_selection_rules.md references non-test model families")

        workspace_base = exec_in_pod(
            pod,
            'printf "%s" "${OPENCODE_WORKSPACE_BASE:-/app/src/data/conversations}"',
        ).strip()
        plan_path = f"{workspace_base}/http/{chat_id}/plan.md"
        plan_text = exec_in_pod(pod, f"cat {shlex.quote(plan_path)}")
        selected_model = selected_model_from_plan(plan_text)
        if selected_model != MODEL:
            raise AssertionError(
                f"planner selected {selected_model}, expected mounted test model {MODEL}\n{plan_text}"
            )

        logs = run_kubectl(
            "-n",
            NAMESPACE,
            "logs",
            f"deployment/{SERVICE}",
            "--all-containers=true",
            "--since=2m",
            check=False,
        ).stdout
        failure_markers = ("Planner Failed", "selected_model is not in models/model_ids.txt")
        if any(marker in logs for marker in failure_markers):
            raise AssertionError(f"recent API logs include planner failure markers:\n{logs[-4000:]}")

        print("[pass] deployed planner used mounted cheap test allowlist and wrote a valid plan")
        print(f"[pass] selected_model={selected_model}")
        return 0
    finally:
        if port_forward is not None:
            port_forward.terminate()
            try:
                port_forward.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
                port_forward.wait(timeout=5)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        raise SystemExit(1)
