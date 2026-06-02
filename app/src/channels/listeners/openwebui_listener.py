




from __future__ import annotations
import asyncio
import threading
import logging
from typing import TYPE_CHECKING, Callable

import httpx

from config import OPENWEBUI_POLL_INTERVAL

if TYPE_CHECKING:
    from storage.models import WebhookRecord

logger = logging.getLogger(__name__)

def create_openwebui_listener(
    record: "WebhookRecord",
    stop_event: threading.Event,
) -> Callable[[], None]:












    config = record.get_config()
    base_url = config["base_url"].rstrip("/")
    channel_id = config["channel_id"]
    api_key = config["api_key"]
    conversation_id = record.conversation_id
    webhook_id = record.webhook_id

    def run() -> None:

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def poll():

            last_seen_id: str | None = None

            async with httpx.AsyncClient(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            ) as client:
                while not stop_event.is_set():
                    try:
                        params = {}
                        if last_seen_id:
                            params["after"] = last_seen_id

                        resp = await client.get(
                            f"/api/v1/channels/{channel_id}/messages",
                            params=params,
                        )

                        if resp.status_code == 200:
                            data = resp.json()
                            messages = data.get("data", data.get("messages", []))

                            for msg in messages:
                                if msg.get("role") == "assistant":
                                    continue

                                from channels.debounce import push_message

                                author = "unknown"
                                user = msg.get("user", {})
                                if isinstance(user, dict):
                                    author = user.get("name", user.get("email", "unknown"))
                                elif isinstance(user, str):
                                    author = user

                                attachments = []
                                for f in msg.get("files", []):
                                    file_url = f.get("url", "")
                                    if file_url and not file_url.startswith("http"):
                                        file_url = f"{base_url}{file_url}"
                                    attachments.append({
                                        "filename": f.get("name", "file"),
                                        "url": file_url,
                                        "content_type": f.get(
                                            "type",
                                            "application/octet-stream",
                                        ),
                                    })

                                push_message(
                                    conversation_id=conversation_id,
                                    message={
                                        "platform": "openwebui",
                                        "webhook_id": webhook_id,
                                        "conversation_id": conversation_id,
                                        "author": author,
                                        "content": msg.get("content", ""),
                                        "attachments": attachments,
                                        "channel_ref": {
                                            "base_url": base_url,
                                            "channel_id": channel_id,
                                            "api_key": api_key,
                                        },
                                        "timestamp": msg.get("timestamp", ""),
                                    },
                                )
                                logger.debug(
                                    f"OpenWebUI message from {author} "
                                    f"in {webhook_id}: {msg.get('content', '')[:50]}..."
                                )
                                last_seen_id = msg.get("id", last_seen_id)

                        elif resp.status_code == 304:
                            pass
                        elif resp.status_code == 401:
                            logger.error(
                                f"OpenWebUI auth failed for {webhook_id}: "
                                "check API key"
                            )
                            break
                        elif resp.status_code == 404:
                            logger.error(
                                f"OpenWebUI channel not found for {webhook_id}: "
                                f"channel {channel_id}"
                            )
                            break
                        else:
                            logger.warning(
                                f"OpenWebUI poll returned {resp.status_code} "
                                f"for {webhook_id}"
                            )

                    except httpx.TimeoutException:
                        logger.debug(f"OpenWebUI poll timeout for {webhook_id}")
                    except httpx.RequestError as e:
                        logger.error(
                            f"OpenWebUI connection error for {webhook_id}: {e}"
                        )
                    except Exception as e:
                        logger.error(
                            f"OpenWebUI listener error for {webhook_id}: {e}"
                        )

                    await asyncio.sleep(OPENWEBUI_POLL_INTERVAL)

        try:
            loop.run_until_complete(poll())
        except Exception as e:
            logger.error(f"OpenWebUI listener error for {webhook_id}: {e}")
        finally:
            loop.close()
            logger.info(f"OpenWebUI listener stopped for {webhook_id}")

    return run
