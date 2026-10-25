import json
import time

import httpx
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from services.coach_discord.app import RelaySettings, create_app
from services.coach_discord.discord_api import Discord, chunks


KEY = SigningKey.generate()


class FakeCoach:
    def __init__(self):
        self.asked = []
        self.resets = []

    async def ask(self, person, athlete, conversation_id, text):
        self.asked.append((person, athlete, conversation_id, text))
        return "x" * 2500

    async def reset(self, person, conversation_id):
        self.resets.append((person, conversation_id))


def signed(client, payload):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = KEY.sign(timestamp.encode() + body).signature.hex()
    return client.post("/interactions", content=body, headers={"X-Signature-Ed25519": signature, "X-Signature-Timestamp": timestamp, "Content-Type": "application/json"})


def build():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(200, json={})

    settings = RelaySettings(coach_url="http://coach", internal_token="t", bot_token="", public_key=KEY.verify_key.encode().hex(), application_id="app-1", persons={"42": "operator"})
    coach = FakeCoach()
    return create_app(settings, Discord(transport=httpx.MockTransport(handler)), coach), coach, sent


def command(name, user="42", message=None):
    data = {"name": name, **({"options": [{"name": "message", "type": 3, "value": message}]} if message else {})}
    return {"type": 2, "token": "itok", "channel_id": "c9", "member": {"user": {"id": user}}, "data": data}


def test_ping_and_signature():
    app, _, _ = build()
    with TestClient(app) as client:
        assert signed(client, {"type": 1}).json() == {"type": 1}
        bad = client.post("/interactions", content=b'{"type":1}', headers={"X-Signature-Ed25519": "00" * 64, "X-Signature-Timestamp": "1"})
        assert bad.status_code == 401


def test_coach_command_defers_then_replies_in_chunks():
    app, coach, sent = build()
    with TestClient(app) as client:
        assert signed(client, command("coach", message="Am I ready?")).json() == {"type": 5}
        for _ in range(100):
            if len(sent) == 2:
                break
            time.sleep(0.02)
    assert coach.asked == [("operator", "operator", "powerlifting:operator:discord:c9", "Am I ready?")]
    assert sent[0][0] == "PATCH" and sent[0][1] == "/api/v10/webhooks/app-1/itok/messages/@original"
    assert sent[1][0] == "POST" and len(sent[0][2]["content"]) + len(sent[1][2]["content"]) == 2500


def test_unlinked_user_and_reset():
    app, coach, _ = build()
    with TestClient(app) as client:
        assert "not linked" in signed(client, command("coach", user="7", message="hi")).json()["data"]["content"]
        assert signed(client, command("coach-reset")).json()["data"]["flags"] == 64
    assert coach.resets == [("operator", "powerlifting:operator:discord:c9")]


def test_chunks_respect_limit():
    parts = chunks(("line\n" * 900))
    assert all(len(part) <= 2000 for part in parts) and "".join(parts).count("line") == 900
