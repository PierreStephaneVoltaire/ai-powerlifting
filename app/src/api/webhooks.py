
from __future__ import annotations
import logging
from typing import Literal, Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage.factory import get_webhook_store
from storage.models import WebhookRecord
from channels.manager import start_listener, stop_listener

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

class DiscordConfig(BaseModel):

    bot_token: str = Field(..., description="Discord bot token")
    channel_id: str = Field(..., description="Discord channel ID to listen to")
    pinned_specialist: Optional[str] = Field(
        None,
        description="Specialist slug to lock this channel to. Leave blank for normal planner-based routing.",
    )
    self_aware: bool = Field(
        default=False,
        description="Mark this channel as an IF self-aware meta channel. Injects IF codebase context into every conversation in this channel.",
    )

class OpenWebUIConfig(BaseModel):

    base_url: str = Field(..., description="OpenWebUI server base URL")
    channel_id: str = Field(..., description="OpenWebUI channel ID")
    api_key: str = Field(..., description="OpenWebUI API key")

class RegisterWebhookRequest(BaseModel):

    platform: Literal["discord", "openwebui"] = Field(
        ..., description="Platform type"
    )
    label: str = Field(
        ..., description="Human-readable label for this channel"
    )
    discord: Optional[DiscordConfig] = Field(
        None, description="Discord configuration (required if platform is discord)"
    )
    openwebui: Optional[OpenWebUIConfig] = Field(
        None, description="OpenWebUI configuration (required if platform is openwebui)"
    )

class WebhookResponse(BaseModel):

    webhook_id: str
    conversation_id: str
    platform: str
    label: str
    status: str
    pinned_specialist: str = ""
    self_aware: bool = False

class WebhookListResponse(BaseModel):

    webhooks: List[WebhookResponse]
    total: int

@router.post("/register", response_model=WebhookResponse)
async def register_webhook(req: RegisterWebhookRequest):

    if req.platform == "discord" and req.discord is None:
        raise HTTPException(
            status_code=400,
            detail="discord config required when platform is 'discord'"
        )
    if req.platform == "openwebui" and req.openwebui is None:
        raise HTTPException(
            status_code=400,
            detail="openwebui config required when platform is 'openwebui'"
        )
    
    platform_config = (req.discord or req.openwebui)
    config = platform_config.model_dump()
    pinned_specialist = ""
    if req.platform == "discord" and req.discord and req.discord.pinned_specialist:
        pinned_specialist = req.discord.pinned_specialist.strip()
    if pinned_specialist:
        try:
            from agent.specialists import get_specialist
            if get_specialist(pinned_specialist) is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown specialist slug: '{pinned_specialist}'. "
                           "Check /v1/chat/completions specialist catalog.",
                )
        except HTTPException:
            raise
        except Exception:
            pass 

    self_aware = bool(req.discord.self_aware) if req.platform == "discord" and req.discord else False

    record = WebhookRecord(
        platform=req.platform,
        label=req.label,
        pinned_specialist=pinned_specialist,
        self_aware=self_aware,
    )
    record.set_config(config)

    store = get_webhook_store()
    record = store.create(record)

    logger.info(
        f"Registered webhook {record.webhook_id} "
        f"({req.platform}, {req.label})"
        + (f" locked to specialist={pinned_specialist}" if pinned_specialist else "")
    )

    try:
        start_listener(record)
    except Exception as e:
        logger.error(f"Failed to start listener for {record.webhook_id}: {e}")

    return WebhookResponse(
        webhook_id=record.webhook_id,
        conversation_id=record.conversation_id,
        platform=record.platform,
        label=record.label,
        status="listening" if record.status == "active" else record.status,
        pinned_specialist=record.pinned_specialist,
        self_aware=bool(record.self_aware),
    )

@router.get("/", response_model=WebhookListResponse)
async def list_all_webhooks():

    store = get_webhook_store()
    records = store.list_all()
    
    webhooks = [
        WebhookResponse(
            webhook_id=r.webhook_id,
            conversation_id=r.conversation_id,
            platform=r.platform,
            label=r.label,
            status=r.status,
            pinned_specialist=r.pinned_specialist or "",
            self_aware=bool(r.self_aware),
        )
        for r in records
    ]

    return WebhookListResponse(
        webhooks=webhooks,
        total=len(webhooks),
    )

@router.get("/active", response_model=WebhookListResponse)
async def list_active_webhooks():

    store = get_webhook_store()
    records = store.list_active()

    webhooks = [
        WebhookResponse(
            webhook_id=r.webhook_id,
            conversation_id=r.conversation_id,
            platform=r.platform,
            label=r.label,
            status=r.status,
            pinned_specialist=r.pinned_specialist or "",
            self_aware=bool(r.self_aware),
        )
        for r in records
    ]

    return WebhookListResponse(
        webhooks=webhooks,
        total=len(webhooks),
    )

@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(webhook_id: str):

    store = get_webhook_store()
    record = store.get(webhook_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook not found: {webhook_id}"
        )

    return WebhookResponse(
        webhook_id=record.webhook_id,
        conversation_id=record.conversation_id,
        platform=record.platform,
        label=record.label,
        status=record.status,
        pinned_specialist=record.pinned_specialist or "",
        self_aware=bool(record.self_aware),
    )

@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):

    store = get_webhook_store()
    record = store.get(webhook_id)
    
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook not found: {webhook_id}"
        )
    
    stop_listener(webhook_id)
    
    store.deactivate(webhook_id)
    
    logger.info(f"Deactivated webhook {webhook_id}")
    
    return {
        "status": "deactivated",
        "webhook_id": webhook_id,
    }

@router.post("/{webhook_id}/restart")
async def restart_webhook(webhook_id: str):

    store = get_webhook_store()
    record = store.get(webhook_id)
    
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook not found: {webhook_id}"
        )
    
    if record.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Webhook is not active: {webhook_id}"
        )
    
    try:
        start_listener(record)
    except Exception as e:
        logger.error(f"Failed to restart listener for {webhook_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start listener: {e}"
        )
    
    return {
        "status": "restarted",
        "webhook_id": webhook_id,
    }
