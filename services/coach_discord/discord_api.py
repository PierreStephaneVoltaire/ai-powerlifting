from dataclasses import dataclass

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


API = "https://discord.com/api/v10"
MESSAGE_LIMIT = 2000
COMMANDS = [
    {"name": "coach", "description": "Ask the powerlifting Coach", "type": 1, "options": [{"type": 3, "name": "message", "description": "What to ask", "required": True}]},
    {"name": "coach-reset", "description": "Start a fresh Coach conversation in this channel", "type": 1},
]


@dataclass(frozen=True)
class Application:
    application_id: str
    public_key: str


def verify(public_key: str, signature: str, timestamp: str, body: bytes) -> bool:
    try:
        VerifyKey(bytes.fromhex(public_key)).verify(timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def chunks(text: str) -> list[str]:
    text = text.strip() or "(no reply)"
    parts = []
    while text:
        if len(text) <= MESSAGE_LIMIT:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, MESSAGE_LIMIT)
        cut = cut if cut > MESSAGE_LIMIT // 2 else MESSAGE_LIMIT
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts


class Discord:
    def __init__(self, bot_token: str = "", transport: httpx.AsyncBaseTransport | None = None):
        self.bot_token = bot_token
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=API, timeout=15, transport=self.transport)

    async def application(self) -> Application:
        async with self._client() as client:
            response = await client.get("/applications/@me", headers={"Authorization": "Bot " + self.bot_token})
        response.raise_for_status()
        body = response.json()
        return Application(application_id=body["id"], public_key=body["verify_key"])

    async def register_commands(self, application_id: str, guild_id: str = "") -> list[dict]:
        path = f"/applications/{application_id}/guilds/{guild_id}/commands" if guild_id else f"/applications/{application_id}/commands"
        created = []
        async with self._client() as client:
            for command in COMMANDS:
                response = await client.post(path, json=command, headers={"Authorization": "Bot " + self.bot_token})
                response.raise_for_status()
                created.append(response.json())
        return created

    async def reply(self, application_id: str, interaction_token: str, text: str) -> None:
        first, *rest = chunks(text)
        async with self._client() as client:
            response = await client.patch(f"/webhooks/{application_id}/{interaction_token}/messages/@original", json={"content": first, "allowed_mentions": {"parse": []}})
            response.raise_for_status()
            for part in rest:
                response = await client.post(f"/webhooks/{application_id}/{interaction_token}", json={"content": part, "allowed_mentions": {"parse": []}})
                response.raise_for_status()
