import asyncio
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .coach_client import CoachClient
from .gateway import Gateway, Relay
from .store import Registration, RegistrationStore

logger = logging.getLogger("coach.discord")


class RegisterServer(BaseModel):
    label: str
    bot_token: str
    channel_id: str


def persons_from_env() -> dict[str, str]:
    persons = json.loads(os.getenv("DISCORD_PERSONS", "{}"))
    operator = os.getenv("DISCORD_OPERATOR_ID", "")
    if operator:
        persons.setdefault(operator, os.getenv("OPERATOR_PERSON", "operator"))
    return persons


def store_from_env() -> RegistrationStore:
    return RegistrationStore(
        table_name=os.getenv("DISCORD_STORE_TABLE", "if-webhooks"),
        partition=os.getenv("DISCORD_STORE_PARTITION", "powerlifting"),
        region=os.getenv("AWS_REGION", "ca-central-1"),
    )


def view(registration: Registration, gateway: Gateway) -> dict:
    return {
        "webhook_id": registration.webhook_id,
        "label": registration.label,
        "channel_id": registration.channel_id,
        "status": registration.status,
        "listening": gateway.listening(registration),
    }


def create_app(store: RegistrationStore | None = None, coach: CoachClient | None = None, persons: dict[str, str] | None = None, internal_token: str | None = None, gateway: Gateway | None = None) -> FastAPI:
    internal_token = os.getenv("INTERNAL_API_TOKEN", "") if internal_token is None else internal_token
    coach = coach or CoachClient(os.getenv("COACH_URL", "http://pl-coach:8000"), internal_token)
    relay = Relay(coach, persons_from_env() if persons is None else persons)
    state = {"store": store, "gateway": gateway}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state["store"] = state["store"] or store_from_env()
        state["gateway"] = state["gateway"] or Gateway(relay)
        for registration in await asyncio.to_thread(state["store"].list, True):
            state["gateway"].attach(registration)
        logger.info("Loaded %s Discord registrations", len(state["gateway"].channels))
        yield
        await state["gateway"].close()

    app = FastAPI(title="Powerlifting Coach Discord bot", lifespan=lifespan)

    def authorized(x_internal_token: str = Header(default="")) -> None:
        if not internal_token or not hmac.compare_digest(x_internal_token, internal_token):
            raise HTTPException(401, "Invalid internal token")

    async def found(webhook_id: str) -> Registration:
        registration = await asyncio.to_thread(state["store"].get, webhook_id)
        if registration is None:
            raise HTTPException(404, f"Registration not found: {webhook_id}")
        return registration

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/servers", dependencies=[Depends(authorized)])
    async def register(body: RegisterServer):
        registration = await asyncio.to_thread(state["store"].create, Registration(label=body.label, bot_token=body.bot_token, channel_id=body.channel_id))
        state["gateway"].attach(registration)
        logger.info("Registered Discord channel %s (%s)", registration.channel_id, registration.label)
        return view(registration, state["gateway"])

    @app.get("/v1/servers", dependencies=[Depends(authorized)])
    async def list_servers():
        registrations = await asyncio.to_thread(state["store"].list)
        return {"servers": [view(registration, state["gateway"]) for registration in registrations]}

    @app.delete("/v1/servers/{webhook_id}", dependencies=[Depends(authorized)])
    async def deactivate(webhook_id: str):
        registration = await found(webhook_id)
        state["gateway"].detach(registration)
        await asyncio.to_thread(state["store"].deactivate, webhook_id)
        return {"webhook_id": webhook_id, "status": "inactive"}

    @app.post("/v1/servers/{webhook_id}/restart", dependencies=[Depends(authorized)])
    async def restart(webhook_id: str):
        registration = await found(webhook_id)
        if registration.status != "active":
            raise HTTPException(400, "Registration is not active")
        state["gateway"].detach(registration)
        state["gateway"].attach(registration)
        return view(registration, state["gateway"])

    return app


def main() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
