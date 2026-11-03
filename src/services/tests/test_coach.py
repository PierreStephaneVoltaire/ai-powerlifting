import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from services.coach import principal
from services.coach.app import create_app
from services.coach.config import load
from services.coach.model import Reply


SECRET = "s" * 40
TOKEN = "internal-token"
SERVICES = Path(__file__).resolve().parents[1]


class FakeServices:
    def __init__(self):
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.url.host, request.url.path, dict(request.headers), body))
        principal_claims = principal.verify(SECRET, request.headers["x-pl-principal"], principal_operation(request), request.headers.get("x-person-pk", ""), request.headers.get("x-athlete-pk", "")) if request.url.path != "/internal/access" else None
        if request.url.path == "/internal/access":
            return httpx.Response(200, json={"permissions": ["program:read", "glossary:write"], "competition_scope": {"read": []}})
        if request.url.path == "/operations/glossary_estimate_e1rm":
            assert request.headers["x-if-turn-id"]
            return httpx.Response(200, json={"status": "needs_inference", "execution_id": "exec-1", "challenge_id": "ch-1", "messages": [{"role": "system", "content": "Estimate."}, {"role": "user", "content": "Squat"}], "tools": [{"type": "function", "function": {"name": "report", "parameters": {"type": "object", "properties": {"e1rm_kg": {"type": "number"}}, "required": ["e1rm_kg"]}}}]})
        if request.url.path == "/executions/exec-1":
            assert principal_claims["operation"] == "domain_resume"
            assert body == {"challenge_id": "ch-1", "content": {"e1rm_kg": 200}}
            return httpx.Response(200, json={"status": "succeeded", "result": {"status": "estimated", "estimate": {"e1rm_kg": 200, "basis": "model"}}})
        if request.url.path == "/operations/calculate_dots":
            assert "x-if-turn-id" not in request.headers
            return httpx.Response(200, json={"dots": 412.5})
        return httpx.Response(404, json={"detail": "missing"})


def principal_operation(request: httpx.Request) -> str:
    return "domain_resume" if request.url.path.startswith("/executions/") else request.url.path.rsplit("/", 1)[-1]


class FakeModel:
    def __init__(self):
        self.completions = []
        self.app = None

    async def complete(self, instructions, prompt):
        self.completions.append((instructions, prompt))
        return "```json\n{\"e1rm_kg\": \"heavy\"}\n```" if len(self.completions) == 1 else "{\"e1rm_kg\": 200}"

    async def converse(self, workspace, thread_id, instructions, prompt, tools):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://coach") as client:
            headers = {"Authorization": "Bearer " + tools.token}
            path = httpx.URL(tools.url).path
            listed = (await client.post(path, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=headers)).json()
            names = {tool["name"] for tool in listed["result"]["tools"]}
            assert "identity_resolve" not in names and "calculate_dots" in names
            called = (await client.post(path, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "calculate_dots", "arguments": {"total_kg": 600, "bodyweight_kg": 90, "sex": "male", "_access": {"x": 1}}}}, headers=headers)).json()
            denied = await client.post(path, json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, headers={"Authorization": "Bearer wrong"})
        assert denied.status_code == 401
        dots = json.loads(called["result"]["content"][0]["text"])["dots"]
        return Reply(text=f"{'resumed' if thread_id else 'new'}:{prompt.splitlines()[-1]}:{dots}", thread_id="thread-1")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    monkeypatch.setenv("PL_PRINCIPAL_SECRET", SECRET)
    monkeypatch.setenv("PL_SERVICES_DIR", str(SERVICES))
    monkeypatch.setenv("COACH_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("COACH_URL", "http://coach")
    from services.coach.services import PowerliftingServices

    settings = load()
    fake = FakeServices()
    model = FakeModel()
    app = create_app(settings, model, PowerliftingServices(settings, httpx.MockTransport(fake.handler)))
    model.app = app
    with TestClient(app) as client:
        yield client, fake, model


def headers(person="operator", operation=None, athlete="operator"):
    result = {"X-Internal-Token": TOKEN, "X-Person-Pk": person}
    if operation:
        result["X-PL-Principal"] = principal.sign(SECRET, person, athlete, operation)
    return result


def wait(client, job_id, request_headers):
    for _ in range(200):
        response = client.get(f"/v1/jobs/{job_id}/result", headers=request_headers)
        if response.status_code == 200:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_domain_job_answers_inference_challenges_and_returns_compatible_result(harness):
    client, fake, model = harness
    submitted = client.post("/v1/jobs", json={"kind": "domain", "payload": {"operation": "glossary_estimate_e1rm", "arguments": {"id": "squat"}, "athlete": "operator"}}, headers=headers(operation="glossary_estimate_e1rm"))
    assert submitted.status_code == 202, submitted.text
    job = wait(client, submitted.json()["job_id"], headers(operation="domain_job_read"))
    assert job["status"] == "succeeded", job
    assert json.loads(job["result"]["content"])["estimate"]["e1rm_kg"] == 200
    assert len(model.completions) == 2 and "rejected" in model.completions[1][1]


def test_domain_job_rejects_bad_principal_and_scope(harness):
    client, _, _ = harness
    payload = {"kind": "domain", "payload": {"operation": "glossary_estimate_e1rm", "arguments": {"id": "squat"}, "athlete": "operator"}}
    assert client.post("/v1/jobs", json=payload, headers=headers(operation="program_get")).status_code == 401
    scoped = {"kind": "domain", "payload": {**payload["payload"], "arguments": {"id": "squat", "pk": "someone-else"}}}
    assert client.post("/v1/jobs", json=scoped, headers=headers(operation="glossary_estimate_e1rm")).status_code == 403
    assert client.post("/v1/jobs", json=payload, headers={"X-Person-Pk": "operator"}).status_code == 401


def test_conversation_turn_uses_scoped_tools_and_keeps_thread(harness):
    client, fake, _ = harness
    first = client.post("/v1/conversations/powerlifting:operator:discord:1/turns", json={"messages": [{"role": "user", "content": "What is my DOTS?"}]}, headers=headers())
    assert first.status_code == 202, first.text
    done = wait(client, first.json()["job_id"], headers())
    assert done["status"] == "succeeded", done
    assert done["result"]["content"] == "new:What is my DOTS?:412.5"
    forwarded = next(call for call in fake.calls if call[1] == "/operations/calculate_dots")
    assert "_access" not in forwarded[3]
    second = client.post("/v1/conversations/powerlifting:operator:discord:1/turns", json={"messages": [{"role": "user", "content": "And now?"}]}, headers=headers())
    assert wait(client, second.json()["job_id"], headers())["result"]["content"] == "resumed:And now?:412.5"
    assert client.get(f"/v1/jobs/{second.json()['job_id']}", headers=headers(person="someone")).status_code == 404
    assert client.delete("/v1/conversations/powerlifting:operator:discord:1", headers=headers()).json() == {"reset": True}


def test_tools_refuse_finished_turns(harness):
    client, _, _ = harness
    runner = client.app.state.runner
    job = runner.store.create("operator", "operator", "conversation", "c", {"messages": []})
    job.status = "succeeded"
    runner.store.update(job)
    response = client.post(f"/v1/jobs/{job.job_id}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": "Bearer " + runner.tool_token(job.job_id)})
    assert response.status_code == 409
