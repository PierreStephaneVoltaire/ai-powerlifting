import asyncio
import json
import logging
import os
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .coach_client import CoachClient
from .discord_api import Application, Discord, verify


logger = logging.getLogger("coach.discord")
PING, APPLICATION_COMMAND = 1, 2
PONG, DEFERRED_MESSAGE, MESSAGE = 1, 5, 4
EPHEMERAL = 64


@dataclass(frozen=True)
class RelaySettings:
    coach_url: str
    internal_token: str
    bot_token: str
    public_key: str
    application_id: str
    persons: dict[str, str]


def load() -> RelaySettings:
    persons = json.loads(os.getenv("DISCORD_PERSONS", "{}"))
    operator = os.getenv("DISCORD_OPERATOR_ID", "")
    if operator:
        persons.setdefault(operator, os.getenv("OPERATOR_PERSON", "operator"))
    return RelaySettings(
        coach_url=os.getenv("COACH_URL", "http://pl-coach:8000"),
        internal_token=os.getenv("INTERNAL_API_TOKEN", ""),
        bot_token=os.getenv("DISCORD_TOKEN", ""),
        public_key=os.getenv("DISCORD_PUBLIC_KEY", ""),
        application_id=os.getenv("DISCORD_APPLICATION_ID", ""),
        persons=persons,
    )


def _user_id(interaction: dict) -> str:
    return str(((interaction.get("member") or {}).get("user") or interaction.get("user") or {}).get("id", ""))


def _option(interaction: dict, name: str) -> str:
    return next((str(o.get("value", "")) for o in (interaction.get("data") or {}).get("options") or [] if o.get("name") == name), "")


def _notice(text: str) -> JSONResponse:
    return JSONResponse({"type": MESSAGE, "data": {"content": text, "flags": EPHEMERAL}})


def create_app(settings: RelaySettings | None = None, discord: Discord | None = None, coach: CoachClient | None = None) -> FastAPI:
    settings = settings or load()
    discord = discord or Discord(settings.bot_token)
    coach = coach or CoachClient(settings.coach_url, settings.internal_token)
    app = FastAPI(title="Powerlifting Coach Discord relay")
    app.state.application = Application(settings.application_id, settings.public_key) if settings.public_key and settings.application_id else None
    app.state.tasks = set()

    async def application() -> Application:
        if app.state.application is None:
            app.state.application = await discord.application()
        return app.state.application

    async def answer(interaction: dict, person: str, conversation_id: str, text: str) -> None:
        current = await application()
        try:
            reply = await coach.ask(person, person, conversation_id, text)
        except Exception as exc:
            logger.exception("coach request failed")
            reply = f"The Coach is unavailable right now ({type(exc).__name__})."
        await discord.reply(current.application_id, interaction["token"], reply)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/interactions")
    async def interactions(request: Request):
        current = await application()
        body = await request.body()
        if not verify(current.public_key, request.headers.get("X-Signature-Ed25519", ""), request.headers.get("X-Signature-Timestamp", ""), body):
            raise HTTPException(401, "Invalid request signature")
        interaction = json.loads(body)
        if interaction.get("type") == PING:
            return {"type": PONG}
        if interaction.get("type") != APPLICATION_COMMAND:
            return _notice("Unsupported interaction.")
        person = settings.persons.get(_user_id(interaction))
        if not person:
            return _notice("Your Discord account is not linked to a powerlifting Person yet.")
        conversation_id = f"powerlifting:{person}:discord:{interaction.get('channel_id', 'dm')}"
        command = (interaction.get("data") or {}).get("name")
        if command == "coach-reset":
            await coach.reset(person, conversation_id)
            return _notice("Started a fresh Coach conversation for this channel.")
        if command != "coach":
            return _notice("Unknown command.")
        task = asyncio.create_task(answer(interaction, person, conversation_id, _option(interaction, "message")))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)
        return {"type": DEFERRED_MESSAGE}

    return app


def main() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
