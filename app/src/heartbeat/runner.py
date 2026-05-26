"""Heartbeat runner for proactive operator engagement.

Background task that periodically checks for idle channels and
initiates pondering conversations to maintain engagement.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, time as dt_time, timezone
from typing import TYPE_CHECKING, Any, Optional

from config import (
    HEARTBEAT_IDLE_HOURS,
    HEARTBEAT_COOLDOWN_HOURS,
    HEARTBEAT_QUIET_HOURS,
    LLM_BASE_URL,
    LLM_API_KEY,
    HEARTBEAT_FALLBACK_MODEL,
)
from memory.user_facts import FactCategory

if TYPE_CHECKING:
    from .activity import ActivityTracker
    from storage.models import WebhookRecord
    from storage.protocol import WebhookStore
    from memory.user_facts import UserFactStore
    from routing.cache import ConversationCache
    import httpx

logger = logging.getLogger(__name__)


def load_base_system_prompt() -> str:
    """Load the base system prompt.
    
    Returns:
        Content of main_system_prompt.txt
    """
    from config import PROJECT_ROOT
    path = PROJECT_ROOT / "main_system_prompt.txt"
    if not path.exists():
        path = PROJECT_ROOT / "app" / "main_system_prompt.txt"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to load base system prompt from {path}: {e}")
        return ""


async def call_llm(
    model: str,
    messages: list[dict],
    system_prompt: str,
    max_tokens: int,
    http_client: "httpx.AsyncClient",
) -> Any:
    """Make an LLM API call.
    
    Args:
        model: Model identifier
        messages: Conversation messages
        system_prompt: System prompt text
        max_tokens: Maximum tokens in response
        http_client: HTTP client for API calls
        
    Returns:
        Response object with content attribute
    """
    import httpx
    
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages
        ],
        "max_tokens": max_tokens,
    }
    
    response = await http_client.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    
    class LLMResponse:
        pass
    
    result = LLMResponse()
    result.content = data["choices"][0]["message"]["content"]
    return result


class HeartbeatRunner:
    """Background runner for heartbeat system.
    
    Periodically checks for idle channels and initiates
    pondering conversations.
    
    Example:
        >>> runner = HeartbeatRunner(tracker, store, facts, cache, dispatcher)
        >>> runner.start()
        >>> # ... runs in background ...
        >>> runner.stop()
    """
    
    def __init__(
        self,
        activity_tracker: "ActivityTracker",
        webhook_store: "WebhookStore",
        user_facts_store: "UserFactStore",
        conversation_cache: "ConversationCache",
        http_client: "httpx.AsyncClient",
    ):
        """Initialize the heartbeat runner.
        
        Args:
            activity_tracker: Activity tracker instance
            webhook_store: Webhook persistence store
            user_facts_store: User facts store for context
            conversation_cache: Conversation routing cache
            http_client: HTTP client for LLM calls
        """
        self.activity_tracker = activity_tracker
        self.webhook_store = webhook_store
        self.user_facts_store = user_facts_store
        self.conversation_cache = conversation_cache
        self.http_client = http_client
        self._task: asyncio.Task | None = None
        self._deliver_fn = None
    
    def set_deliver_fn(self, deliver_fn) -> None:
        """Set the delivery function for sending heartbeat messages.
        
        Args:
            deliver_fn: Async function(webhook, content, attachments) -> None
        """
        self._deliver_fn = deliver_fn
    
    def start(self) -> None:
        """Start the heartbeat background loop."""
        if self._task is not None:
            logger.warning("[Heartbeat] Already running")
            return
        
        self._task = asyncio.create_task(self._loop())
        logger.info("[Heartbeat] Runner started")
    
    def stop(self) -> None:
        """Stop the heartbeat background loop."""
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("[Heartbeat] Runner stopped")
    
    async def _loop(self) -> None:
        """Main heartbeat loop - runs every 60 seconds."""
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[Heartbeat] Tick failed: {e}")
            
            await asyncio.sleep(60)
    
    async def _tick(self) -> None:
        """Single heartbeat tick - check for idle channels."""
        if self._in_quiet_hours():
            logger.debug("[Heartbeat] In quiet hours, skipping")
            return
        
        active = self.webhook_store.list_active()
        idle = self.activity_tracker.get_idle_webhooks(
            active_webhooks=active,
            idle_threshold_hours=HEARTBEAT_IDLE_HOURS,
            cooldown_hours=HEARTBEAT_COOLDOWN_HOURS,
        )
        
        logger.info(
            f"[Heartbeat] Tick: {len(active)} active webhooks, "
            f"{len(idle)} idle, {len(active) - len(idle)} on cooldown or active"
        )
        
        for webhook in idle:
            try:
                await self._initiate_pondering(webhook)
            except Exception as e:
                logger.error(
                    f"[Heartbeat] Failed to initiate pondering for "
                    f"{webhook.webhook_id}: {e}"
                )
    
    async def _initiate_pondering(self, webhook: "WebhookRecord") -> None:
        """Initiate a pondering conversation on a channel.
        
        Args:
            webhook: The webhook to send heartbeat to
        """
        config = webhook.get_config()
        channel_id = config.get("channel_id", webhook.conversation_id)
        
        logger.info(
            f"[Heartbeat] Initiating pondering on {webhook.label} "
            f"(channel_id={channel_id})"
        )
        
        # 1. Pin cache to pondering
        self.conversation_cache.pin(channel_id, "pondering")
        logger.info(f"[Cache] Pin set: {channel_id} → pondering")
        
        # 2. Generate contextual opening
        opening = await self._generate_opening(channel_id)
        
        # 3. Dispatch to the channel
        if self._deliver_fn:
            await self._deliver_fn(webhook, opening, [])
        else:
            logger.warning(
                f"[Heartbeat] No delivery function set, cannot send to {webhook.label}"
            )
            return
        
        # 4. Record timestamps
        self.activity_tracker.record_heartbeat(channel_id)
        self.activity_tracker.record_activity(channel_id, webhook.webhook_id)
        
        logger.info(f"[Heartbeat] Pondering initiated on {webhook.label}")
    
    async def _generate_opening(self, cache_key: str) -> str:
        """Generate a contextual opening message for pondering.
        
        Uses stored user facts to create a personalized opening.
        
        Args:
            cache_key: The channel/chat ID
            
        Returns:
            Opening message string
        """
        # Pull relevant user facts
        future = await self._list_facts_async(
            category=FactCategory.FUTURE_DIRECTION,
            context_id=cache_key,
        )
        project = await self._list_facts_async(
            category=FactCategory.PROJECT_DIRECTION,
            context_id=cache_key,
        )
        general = await self._search_facts_async("recent activity goals", context_id=cache_key, limit=3)
        
        all_context = future + project + general
        
        if not all_context:
            # Cold open — no facts stored yet
            return (
                "Statement: Idle period detected. "
                "Initiating baseline calibration. "
                "Query: What are you currently working on?"
            )
        
        # Build context block for the LLM
        context_lines = []
        for f in all_context[:8]:
            date_str = f.updated_at[:10] if f.updated_at else "unknown"
            context_lines.append(
                f"- [{f.category.value}] {f.content} ({date_str})"
            )
        context_block = "\n".join(context_lines)
        
        prompt = (
            f"Generate an opening message for a pondering conversation. "
            f"Stored facts about the operator:\n\n"
            f"{context_block}\n\n"
            f"Generate a single opening (1-3 sentences) in the agent's voice. "
            f"Reference something specific from the facts. Ask a follow-up question. "
            f"Do not be generic."
        )
        
        try:
            from flow.model_catalog import load_model_ids

            model_ids = load_model_ids()
            model = model_ids[0] if model_ids else HEARTBEAT_FALLBACK_MODEL.replace("openrouter/", "")
            
            response = await call_llm(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                system_prompt=load_base_system_prompt(),
                max_tokens=300,
                http_client=self.http_client,
            )
            return response.content
        except Exception as e:
            logger.warning(f"[Heartbeat] Failed to generate opening: {e}")
            # Fallback to cold open
            return (
                "Statement: Idle period detected. "
                "Query: What are you currently working on?"
            )
    
    async def _list_facts_async(
        self,
        category: FactCategory,
        context_id: str = "__global__",
    ) -> list:
        """Async wrapper for listing facts by category."""
        return self.user_facts_store.list_facts(context_id=context_id, category=category)
    
    async def _search_facts_async(
        self,
        query: str,
        context_id: str = "__global__",
        limit: int = 5
    ) -> list:
        """Async wrapper for searching facts."""
        return self.user_facts_store.search(context_id, query, limit=limit)
    
    def _in_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours.
        
        Returns:
            True if in quiet hours, False otherwise
        """
        if not HEARTBEAT_QUIET_HOURS:
            return False
        
        try:
            start_str, end_str = HEARTBEAT_QUIET_HOURS.split("-")
            now = datetime.now(timezone.utc).time()
            start = dt_time.fromisoformat(start_str.strip())
            end = dt_time.fromisoformat(end_str.strip())
            
            if start <= end:
                # Range within same day (e.g., 09:00-17:00)
                return start <= now <= end
            else:
                # Range spans midnight (e.g., 23:00-07:00)
                return now >= start or now <= end
        except (ValueError, TypeError) as e:
            logger.warning(f"[Heartbeat] Invalid quiet hours format: {e}")
            return False
