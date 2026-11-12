import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest
from fastapi.testclient import TestClient

from services.coach import principal
from services.coach.app import create_app
from services.coach.config import load
from services.coach.model import Reply


KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUBLIC = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def sign(person, athlete, operation, destination='pl-coach'):
    now = int(time.time())
    return jwt.encode({'iss': 'pl-security', 'aud': 'powerlifting-services', 'sub': person, 'athlete': athlete, 'operation': operation, 'destination': destination, 'caller': 'cluster.local/ns/powerlifting/sa/powerlifting-app-backend', 'iat': now, 'exp': now + 300}, PRIVATE, algorithm='RS256')
SERVICES = Path(__file__).resolve().parents[1]
AI_OPERATIONS = [record["name"] for path in sorted((SERVICES / "operations").glob("*.json")) for record in json.loads(path.read_text()) if record.get("execution") == "ai"]
OPERATION_AI = {name: {"provider": "openrouter" if name == "glossary_estimate_e1rm" else "chatgpt", "model": "estimate-model" if name == "glossary_estimate_e1rm" else "analysis-model", "effort": "high"} for name in AI_OPERATIONS}
OPERATION_AI["chat_guard"] = {"provider": "chatgpt", "model": "guard-model", "effort": "low"}
GENERAL_ROUTE = json.dumps({"surface": "general", "template_name": None, "intent": "other", "standalone": True, "reason": "training question"})


class FakeServices:
    def __init__(self):
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.url.host, request.url.path, dict(request.headers), body))
        if request.url.path == '/v1/principals':
            return httpx.Response(200, json={'principal': sign('operator', body['athlete'], body['operation'], body['destination'])})
        if request.url.path == '/v1/job-capabilities':
            return httpx.Response(200, json={'capability': 'job-capability'})
        if request.url.path == '/v1/access':
            return httpx.Response(200, json={'context': {'permissions': ['program:read', 'glossary:write'], 'competition_scope': {'read': []}}})
        principal_claims = jwt.decode(request.headers['x-pl-principal'], PUBLIC, algorithms=['RS256'], audience='powerlifting-services', issuer='pl-security')
        if request.url.path == "/operations/glossary_estimate_e1rm":
            assert request.headers["x-if-turn-id"]
            return httpx.Response(200, json={"status": "needs_inference", "execution_id": "exec-1", "challenge_id": "ch-1", "messages": [{"role": "system", "content": "Estimate."}, {"role": "user", "content": "Squat"}], "tools": [{"type": "function", "function": {"name": "report", "parameters": {"type": "object", "properties": {"e1rm_kg": {"type": "number"}}, "required": ["e1rm_kg"]}}}]})
        if request.url.path == "/executions/exec-1":
            assert principal_claims["operation"] == "domain_resume"
            assert body == {"challenge_id": "ch-1", "content": {"e1rm_kg": 200}}
            return httpx.Response(200, json={"status": "succeeded", "result": {"status": "estimated", "estimate": {"e1rm_kg": 200, "basis": "model"}}})
        if request.url.path == "/operations/template_list":
            return httpx.Response(200, json=[])
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

    async def complete(self, ai, instructions, prompt):
        if ai.model == "guard-model":
            return GENERAL_ROUTE
        self.completions.append((instructions, prompt, ai))
        return "```json\n{\"e1rm_kg\": \"heavy\"}\n```" if len(self.completions) == 1 else "{\"e1rm_kg\": 200}"

    async def converse(self, ai, workspace, thread_id, instructions, prompt, tools):
        assert ai.effort == "medium"
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
    monkeypatch.setenv("PL_PRINCIPAL_PUBLIC_KEY", PUBLIC)
    monkeypatch.setenv("PL_SERVICES_DIR", str(SERVICES))
    monkeypatch.setenv("COACH_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("COACH_URL", "http://coach")
    monkeypatch.setenv("COACH_PROVIDERS", json.dumps({"chatgpt": {"auth": "chatgpt", "max_concurrent": 1}, "openrouter": {"auth": "api_key", "base_url": "https://openrouter.example/v1", "max_concurrent": 1}}))
    monkeypatch.setenv("COACH_PROVIDER_KEYS", json.dumps({"openrouter": "router-key"}))
    monkeypatch.setenv("COACH_CONVERSATION_AI", json.dumps({"provider": "chatgpt", "model": "chat-model", "effort": "medium"}))
    monkeypatch.setenv("COACH_OPERATION_AI", json.dumps(OPERATION_AI))
    from services.coach.services import PowerliftingServices

    settings = load()
    fake = FakeServices()
    model = FakeModel()
    app = create_app(settings, model, PowerliftingServices(settings, httpx.MockTransport(fake.handler)))
    model.app = app
    with TestClient(app) as client:
        yield client, fake, model


def headers(person="operator", operation="conversation_turn", athlete="operator"):
    return {"X-Person-Pk": person, "X-PL-Principal": sign(person, athlete, operation),
            "X-PL-Access-Context": json.dumps({"person": person, "athlete": athlete, "operation": operation, "context": {}})}


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
    assert {(ai.provider, ai.model, ai.effort) for _, _, ai in model.completions} == {("openrouter", "estimate-model", "high")}


def test_domain_job_rejects_bad_principal_and_scope(harness):
    client, _, _ = harness
    payload = {"kind": "domain", "payload": {"operation": "glossary_estimate_e1rm", "arguments": {"id": "squat"}, "athlete": "operator"}}
    assert client.post("/v1/jobs", json=payload, headers=headers(operation="program_get")).status_code == 401
    scoped = {"kind": "domain", "payload": {**payload["payload"], "arguments": {"id": "squat", "pk": "someone-else"}}}
    assert client.post("/v1/jobs", json=scoped, headers=headers(operation="glossary_estimate_e1rm")).status_code == 403
    assert client.post("/v1/jobs", json=payload, headers={"X-Person-Pk": "operator"}).status_code == 403


def test_conversation_turn_uses_scoped_tools_and_keeps_thread(harness):
    client, fake, _ = harness
    first = client.post("/v1/conversations/powerlifting:operator:discord:1/turns", json={"messages": [{"role": "user", "content": "What is my DOTS?"}]}, headers=headers())
    assert first.status_code == 202, first.text
    done = wait(client, first.json()["job_id"], headers(operation="domain_job_read"))
    assert done["status"] == "succeeded", done
    assert done["result"]["content"] == "new:What is my DOTS?:412.5"
    forwarded = next(call for call in fake.calls if call[1] == "/operations/calculate_dots")
    assert "_access" not in forwarded[3]
    second = client.post("/v1/conversations/powerlifting:operator:discord:1/turns", json={"messages": [{"role": "user", "content": "And now?"}]}, headers=headers())
    assert wait(client, second.json()["job_id"], headers(operation="domain_job_read"))["result"]["content"] == "resumed:And now?:412.5"
    assert client.get(f"/v1/jobs/{second.json()['job_id']}", headers=headers(person="someone", operation="domain_job_read")).status_code == 404
    assert client.delete("/v1/conversations/powerlifting:operator:discord:1", headers=headers(operation="conversation_reset")).json() == {"reset": True}


def test_tools_refuse_finished_turns(harness):
    client, _, _ = harness
    runner = client.app.state.runner
    job = runner.store.create("operator", "operator", "conversation", "c", {"messages": []})
    job.status = "succeeded"
    runner.store.update(job)
    response = client.post(f"/v1/jobs/{job.job_id}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Authorization": "Bearer " + runner.tool_token(job.job_id)})
    assert response.status_code == 409


def test_coach_refuses_to_start_without_model_settings_for_every_ai_operation(harness, monkeypatch):
    from services.coach.runner import Runner
    settings = load()
    with pytest.raises(ValueError, match="glossary_estimate_e1rm"):
        Runner(replace(settings, operation_ai={k: v for k, v in settings.operation_ai.items() if k != "glossary_estimate_e1rm"}), FakeModel(), None, None)


def test_coach_refuses_unknown_provider(harness):
    from services.coach.runner import Runner
    settings = load()
    ai = settings.operation_ai["glossary_estimate_e1rm"]
    with pytest.raises(ValueError, match="anthropic"):
        Runner(replace(settings, operation_ai={**settings.operation_ai, "glossary_estimate_e1rm": replace(ai, provider="anthropic")}), FakeModel(), None, None)


def test_api_key_provider_runs_codex_as_the_harness_with_its_own_key(harness, tmp_path):
    from services.coach.model import CodexModel, PROVIDER_KEY_ENV
    settings = load()
    model = CodexModel(tmp_path, settings.providers)
    routed = model._config(tmp_path, (), "openrouter")
    assert routed.env[PROVIDER_KEY_ENV] == "router-key" and routed.env.get("COACH_PROVIDER_KEYS") == ""
    assert 'model_provider="openrouter"' in routed.config_overrides
    assert not any(item.startswith("forced_login_method") for item in routed.config_overrides)
    assert 'forced_login_method="chatgpt"' in model._config(tmp_path, (), "chatgpt").config_overrides
