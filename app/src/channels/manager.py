




from __future__ import annotations
import threading
import logging
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from storage.models import WebhookRecord

logger = logging.getLogger(__name__)

_listeners: Dict[str, Dict[str, Any]] = {}

def start_listener(record: "WebhookRecord") -> None:








    wid = record.webhook_id

    if wid in _listeners:
        logger.warning(f"Listener {wid} already running. Skipping.")
        return

    stop_event = threading.Event()
    platform = record.platform

    if platform == "discord":
        from channels.listeners.discord_listener import create_discord_listener
        target = create_discord_listener(record, stop_event)

    elif platform == "openwebui":
        from channels.listeners.openwebui_listener import create_openwebui_listener
        target = create_openwebui_listener(record, stop_event)

    else:
        logger.error(f"Unknown platform: {platform}")
        return

    thread = threading.Thread(
        target=target,
        name=f"listener-{wid}",
        daemon=True,
    )
    thread.start()

    _listeners[wid] = {
        "thread": thread,
        "stop_event": stop_event,
    }
    logger.info(
        f"Started {platform} listener for {wid} ({record.label})"
    )

def stop_listener(webhook_id: str) -> None:





    entry = _listeners.pop(webhook_id, None)
    if entry is None:
        return
    
    entry["stop_event"].set()
    entry["thread"].join(timeout=10)
    logger.info(f"Stopped listener for {webhook_id}")

def start_all_active(records: list["WebhookRecord"]) -> None:







    started = 0
    for record in records:
        if record.status == "active":
            start_listener(record)
            started += 1
    
    logger.info(f"Started {started} active listeners from persisted state")

def stop_all() -> None:




    for wid in list(_listeners.keys()):
        stop_listener(wid)
    
    logger.info("All listeners stopped")

def get_active_listener_count() -> int:





    return len(_listeners)

def is_listener_active(webhook_id: str) -> bool:








    return webhook_id in _listeners
