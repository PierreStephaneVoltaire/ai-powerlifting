import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .coach_client import CoachClient
from .gateway import Gateway, Relay
from .store import Registration, RegistrationStore
from .users import UserDirectory

logger = logging.getLogger("coach.discord")


class RegisterServer(BaseModel):
    label: str
    bot_token: str
    channel_id: str


def directory_from_env() -> UserDirectory:
    return UserDirectory(table_name=os.getenv("IF_USER_TABLE", "if-user"), region=os.getenv("AWS_REGION", "ca-central-1"))


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


def create_app(store: RegistrationStore | None = None, coach: CoachClient | None = None, gateway: Gateway | None = None, directory: UserDirectory | None = None) -> FastAPI:
    coach = coach or CoachClient(os.getenv("COACH_URL", "http://pl-coach:8000"))
    relay = Relay(coach, directory or directory_from_env())
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

    def authorized(x_pl_access_context: str = Header(default="")) -> None:
        try:
            context = json.loads(x_pl_access_context)
            if not isinstance(context, dict) or not str(context.get('workload', '')).endswith('/sa/powerlifting-app-backend'):
                raise ValueError('Unauthorized workload')
        except (TypeError, ValueError) as exc:
            raise HTTPException(403, 'Verified workload required') from exc

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
