from __future__ import annotations
import asyncio
import os
import subprocess
import sys
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, PlainTextResponse

from config import HOST, PORT, SANDBOX_PATH, MEMORY_DB_PATH, PERSISTENCE_DIR, STORAGE_DB_PATH
from config import HEARTBEAT_ENABLED, HEARTBEAT_IDLE_HOURS, HEARTBEAT_COOLDOWN_HOURS
from config import REFLECTION_ENABLED
from config import MODEL_STATS_REFRESH_INTERVAL, MODEL_SEED_INTERVAL
from config import OPENROUTER_API_KEY
from config import SCRIPTS_PATH
from api.models import router as models_router
from api.completions import router as completions_router
from api.files import router as files_router, get_sandbox_directory
from api.webhooks import router as webhooks_router
from api.directives import router as directives_router
from api.admin import router as admin_router
from api.template_imports import router as template_imports_router
from presets.loader import get_preset_manager
from mcp_servers.config import validate_mcp_config
from storage.factory import init_store, close_store, get_webhook_store, init_directive_store
from channels.debounce import init_debounce
from channels.manager import start_all_active, stop_all
from logging_config import setup_logging, get_logger, RequestLoggingMiddleware

logger = get_logger(__name__)

http_client: Optional[httpx.AsyncClient] = None

heartbeat_runner = None

reflection_engine = None

sandbox_manager = None

_stats_refresh_task = None


async def _deliver_heartbeat(webhook, content: str, attachments: list) -> None:

    from channels.delivery import deliver_to_channel
    from channels.chunker import chunk_response
    
    config = webhook.get_config()
    platform = webhook.platform
    channel_id = config.get("channel_id", webhook.conversation_id)
    
    logger.info(f"Delivering heartbeat to {webhook.label} (channel_id={channel_id})")
    
    if platform == "discord":
        try:
            from channels.listeners.discord_listener import get_discord_client
            client = get_discord_client()
            if client:
                import discord
                channel = client.get_channel(int(channel_id))
                if channel and isinstance(channel, discord.TextChannel):
                    chunks = chunk_response(content)
                    await deliver_to_channel(
                        platform=platform,
                        channel_ref=channel,
                        chunks=chunks,
                        attachments=attachments,
                    )
                    return
        except Exception as e:
            logger.warning(f"Discord heartbeat delivery failed: {e}")
            return
    
    elif platform == "openwebui":
        from channels.delivery import deliver_to_openwebui
        chunks = chunk_response(content)
        await deliver_to_openwebui(
            api_url=config.get("api_url"),
            channel_id=channel_id,
            chunks=chunks,
            attachments=attachments,
        )
        return
    
    logger.warning(f"Unknown platform for heartbeat: {platform}")


@asynccontextmanager
async def lifespan(app: FastAPI):

    global http_client
    
    setup_logging()
    
    logger.info("Initializing IF Prototype A1...")
    
    http_client = httpx.AsyncClient(
        timeout=120.0,
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=60.0
        )
    )
    app.state.http_client = http_client
    logger.info("HTTP client initialized")
    
    logger.info("Loading presets...")
    preset_manager = get_preset_manager()
    try:
        preset_manager.load_presets()
    except RuntimeError as e:
        logger.error(f"Failed to load presets: {e}")
        raise

    try:
        generator = Path(SCRIPTS_PATH) / "generate_opencode_agents.py"
        if generator.exists():
            result = subprocess.run(
                [sys.executable, str(generator)],
                capture_output=True,
                text=True,
                timeout=60,
                env=os.environ.copy(),
            )
            if result.returncode == 0:
                logger.info(result.stdout.strip() or "Generated opencode agent files")
            else:
                logger.warning("opencode agent generation failed: %s", result.stderr.strip())
        else:
            logger.warning("opencode agent generator not found at %s", generator)
    except Exception as e:
        logger.warning(f"opencode agent generation failed: {e}")
    
    sandbox_dir = get_sandbox_directory()
    logger.info(f"Sandbox directory: {sandbox_dir}")
    
    memory_db_path = Path(MEMORY_DB_PATH)
    memory_db_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Memory database directory: {memory_db_path}")
    
    persistence_path = Path(PERSISTENCE_DIR)
    persistence_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Conversation persistence directory: {persistence_path}")
    
    try:
        validate_mcp_config()
        logger.info("MCP configuration validated")
    except ValueError as e:
        logger.warning(f"MCP configuration error: {e}")
    
    try:
        from memory import get_user_fact_store
        user_facts_store = get_user_fact_store()
        facts_count = user_facts_store.active_count
        count_str = str(facts_count) if facts_count >= 0 else "count unavailable"
        logger.info(f"User facts store initialized ({count_str} active facts)")
        
        logger.info("Warming up embedding model...")
        try:
            from config import REFLECTION_CONTEXT_ID
            user_facts_store.search(REFLECTION_CONTEXT_ID, "__warmup_query__", limit=1)
            logger.info("Embedding model ready")
        except Exception as warmup_error:
            logger.warning(f"Embedding model warmup failed: {warmup_error}")
    except ImportError as e:
        logger.warning(f"User facts store not available: {e}")
        logger.warning("Install chromadb to enable user facts: pip install chromadb")
    except Exception as e:
        logger.warning(f"User facts store initialization failed: {e}")
    
    try:
        from .memory import get_memory_store
        if get_memory_store:
            memory_store = get_memory_store()
            memory_count = memory_store.count()
            logger.info(f"Legacy memory store initialized ({memory_count} memories)")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Legacy memory store initialization failed: {e}")

    # MCP tool server initialization
    try:
        from mcp_runtime import init_mcp_manager

        manager = init_mcp_manager()
        await manager.start_all()
        logger.info("MCP tools loaded: %s tools", len(manager.list_tool_names()))
    except Exception as e:
        logger.warning(f"MCP tool initialization failed: {e}")

    try:
        import nltk
        nltk.data.find("corpora/stopwords")
        logger.info("NLTK stopwords corpus found")
    except LookupError:
        logger.info("Downloading NLTK stopwords corpus...")
        import nltk
        nltk.download("stopwords", quiet=True)
        logger.info("NLTK stopwords downloaded")
    except ImportError:
        logger.warning("nltk not installed, topic shift heuristic will use basic filtering")
    
    try:
        storage_db_path = Path(STORAGE_DB_PATH)
        storage_db_path.parent.mkdir(parents=True, exist_ok=True)
        init_store()
        logger.info(f"Storage backend initialized at {STORAGE_DB_PATH}")
    except Exception as e:
        logger.error(f"Storage initialization failed: {e}")
        raise
    
    try:
        init_directive_store()
        logger.info("Directive store initialized successfully")
    except Exception as e:
        logger.error(f"CRITICAL: Directive store initialization failed: {e}")
        logger.error("The server will continue but directives will NOT be available in system prompts")
        # Optionally raise here if directives are critical:
        # raise

    # Model registry initialization + OpenRouter refresh
    try:
        from storage.factory import init_model_registry, get_model_registry
        init_model_registry()
        logger.info("Model registry initialized")
    except Exception as e:
        logger.warning(f"Model registry initialization failed: {e}")

    try:
        from pathlib import Path as _Path
        from config import MODELS_PATH
        _models_file = _Path(MODELS_PATH) / "model_ids.txt"
        if _models_file.exists():
            logger.info(f"[ModelRegistry] Refreshing model metadata from OpenRouter API (file={_models_file})...")
            _seed_path = _Path(SCRIPTS_PATH) / "seed_models.py"
            if _seed_path.exists():
                import importlib.util as _ilu
                _result = subprocess.run(
                    [sys.executable, str(_seed_path), str(_models_file)],
                    capture_output=True, text=True, timeout=300,
                    env={**os.environ, "MODELS_FILE": str(_models_file)},
                )
                if _result.returncode == 0:
                    logger.info(f"[ModelRegistry] Seed complete:\n{_result.stdout.strip()}")
                    # Reload registry cache with newly seeded data
                    try:
                        from storage.factory import get_model_registry, init_model_registry
                        try:
                            _reg = get_model_registry()
                        except RuntimeError:
                            init_model_registry()
                            _reg = get_model_registry()
                        _reg.load()
                        logger.info(f"[ModelRegistry] Cache refreshed after seed: {len(_reg._cache)} models")
                    except Exception as _reg_err:
                        logger.warning(f"[ModelRegistry] Post-seed cache reload failed: {_reg_err}")
                else:
                    logger.warning(f"[ModelRegistry] Seed failed (rc={_result.returncode}): {_result.stderr.strip()}")
            else:
                logger.warning(f"[ModelRegistry] Seed script not found at {_seed_path}")
        else:
            logger.info(f"[ModelRegistry] No models file at {_models_file}, skipping refresh")
    except Exception as e:
        logger.warning(f"[ModelRegistry] Startup refresh failed: {e}")

    # Periodic endpoint stats refresh (latency/throughput)
    global _stats_refresh_task

    async def _periodic_stats_refresh():
        from storage.factory import get_model_registry
        while True:
            await asyncio.sleep(MODEL_STATS_REFRESH_INTERVAL)
            try:
                registry = get_model_registry()
                if registry:
                    registry.refresh_endpoint_stats(OPENROUTER_API_KEY)
            except Exception as e:
                logger.warning(f"[ModelRegistry] Periodic stats refresh failed: {e}")

    async def _periodic_model_seed():
        from pathlib import Path as _Path
        from config import MODELS_PATH
        _models_file = _Path(MODELS_PATH) / "model_ids.txt"
        _seed_path = _Path(SCRIPTS_PATH) / "seed_models.py"
        if not _models_file.exists() or not _seed_path.exists():
            logger.warning("[ModelRegistry] Periodic seed skipped: models file or seed script missing")
            return
        while True:
            await asyncio.sleep(MODEL_SEED_INTERVAL)
            try:
                result = subprocess.run(
                    [sys.executable, str(_seed_path), str(_models_file)],
                    capture_output=True, text=True, timeout=300,
                    env={**os.environ, "MODELS_FILE": str(_models_file)},
                )
                if result.returncode == 0:
                    logger.info(f"[ModelRegistry] Periodic seed complete")
                else:
                    logger.warning(f"[ModelRegistry] Periodic seed failed (rc={result.returncode}): {result.stderr.strip()[:200]}")
            except Exception as e:
                logger.warning(f"[ModelRegistry] Periodic seed error: {e}")

    try:
        from storage.factory import get_model_registry
        registry = get_model_registry()
        if registry:
            # Run initial refresh in background (don't block startup)
            asyncio.create_task(_periodic_stats_refresh())
            asyncio.create_task(_periodic_model_seed())
            logger.info(f"Model stats refresh started (interval={MODEL_STATS_REFRESH_INTERVAL}s)")
            logger.info(f"Model seed refresh started (interval={MODEL_SEED_INTERVAL}s)")
    except Exception as e:
        logger.warning(f"Model stats refresh init failed: {e}")

    try:
        init_debounce(asyncio.get_running_loop())
        logger.info("Debounce system initialized")
    except Exception as e:
        logger.warning(f"Debounce initialization failed: {e}")
    
    try:
        store = get_webhook_store()
        active_records = store.list_active()
        start_all_active(active_records)
        logger.info(f"Resumed {len(active_records)} active channel listeners")
    except Exception as e:
        logger.warning(f"Failed to resume listeners: {e}")
    
    global heartbeat_runner
    if HEARTBEAT_ENABLED:
        try:
            from heartbeat.activity import ActivityTracker
            from heartbeat.runner import HeartbeatRunner
            
            store = get_webhook_store()
            activity_tracker = ActivityTracker(store._backend)
            
            try:
                from memory import get_user_fact_store
                user_facts_store = get_user_fact_store()
            except Exception:
                user_facts_store = None
            
            from routing.cache import get_cache
            conversation_cache = get_cache()
            
            heartbeat_runner = HeartbeatRunner(
                activity_tracker=activity_tracker,
                webhook_store=store,
                user_facts_store=user_facts_store,
                conversation_cache=conversation_cache,
                http_client=http_client,
            )
            
            heartbeat_runner.set_deliver_fn(_deliver_heartbeat)
            
            heartbeat_runner.start()
            logger.info(f"Heartbeat system started (idle={HEARTBEAT_IDLE_HOURS}h, cooldown={HEARTBEAT_COOLDOWN_HOURS}h)")
        except Exception as e:
            logger.warning(f"Heartbeat initialization failed: {e}")
    
    global reflection_engine
    if REFLECTION_ENABLED:
        try:
            from agent.reflection import ReflectionEngine, get_reflection_engine
            from agent.reflection.engine import _reflection_engine as reflection_engine_singleton
            
            try:
                from memory import get_user_fact_store
                user_facts_store = get_user_fact_store()
            except Exception as store_error:
                logger.warning(f"Cannot init reflection engine - user facts store unavailable: {store_error}")
                user_facts_store = None
            
            if user_facts_store:
                reflection_engine = ReflectionEngine(
                    store=user_facts_store,
                    http_client=http_client,
                )
                reflection_engine.start()
                
                import agent.reflection.engine as re_module
                re_module._reflection_engine = reflection_engine
                
                logger.info("Reflection engine started")
        except Exception as e:
            logger.warning(f"Reflection engine initialization failed: {e}")
    
    from app_sandbox import init_local_sandbox
    sandbox_manager = init_local_sandbox()
    logger.info(f"[Sandbox] LocalSandbox initialized at {sandbox_manager.workspace_base}")
    
    logger.info(f"Server ready on {HOST}:{PORT}")
    
    yield

    sandbox_manager.close()
    logger.info("[Sandbox] LocalSandboxManager closed")
    
    if reflection_engine:
        reflection_engine.stop()
        logger.info("Reflection engine stopped")
    
    if heartbeat_runner:
        heartbeat_runner.stop()
        logger.info("Heartbeat runner stopped")

    if _stats_refresh_task:
        _stats_refresh_task.cancel()
        logger.info("Model stats refresh stopped")

    try:
        from mcp_runtime import shutdown_mcp_manager

        await shutdown_mcp_manager()
        logger.info("MCP tool servers stopped")
    except Exception as e:
        logger.warning(f"MCP shutdown failed: {e}")
    
    stop_all()
    logger.info("All channel listeners stopped")
    
    close_store()
    logger.info("Storage backend closed")
    
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")


app = FastAPI(
    title="IF Prototype A1 - Agent API",
    description="OpenAI-compatible API with intelligent routing to OpenRouter presets",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)



app.include_router(models_router)
app.include_router(completions_router)
app.include_router(files_router)
app.include_router(webhooks_router)
app.include_router(directives_router)
app.include_router(admin_router)
app.include_router(template_imports_router)



@app.get("/health")
async def health_check():

    preset_manager = get_preset_manager()
    
    user_facts_status = "unavailable"
    user_facts_count = 0
    try:
        from memory import get_user_fact_store
        store = get_user_fact_store()
        user_facts_status = "active"
        user_facts_count = store.active_count
    except Exception:
        pass
    
    memory_status = "unavailable"
    memory_count = 0
    try:
        from memory import get_memory_store
        store = get_memory_store()
        memory_status = "active"
        memory_count = store.count()
    except Exception:
        pass
    
    from channels.manager import get_active_listener_count
    from channels.debounce import get_all_buffer_sizes
    active_listeners = get_active_listener_count()
    buffer_sizes = get_all_buffer_sizes()
    
    from routing.cache import get_cache
    cache = get_cache()
    cached_conversations = len(cache._cache)
    pinned_conversations = sum(1 for v in cache._cache.values() if v.pinned)
    
    heartbeat_status = "inactive"
    if heartbeat_runner and heartbeat_runner._task:
        heartbeat_status = "active"
    
    return {
        "status": "healthy",
        "service": "if-prototype-a1",
        "features": {
            "routing": "active",
            "interceptor": "active",
            "commands": "active",
            "attachments": "active",
            "user_facts_store": user_facts_status,
            "user_facts_count": user_facts_count,
            "presets_loaded": preset_manager.is_initialized(),
            "preset_count": len(preset_manager.get_all_presets()),
            "channel_system": "active",
            "active_listeners": active_listeners,
            "pending_messages": sum(buffer_sizes.values()),
            "heartbeat": heartbeat_status,
            "heartbeat_idle_hours": HEARTBEAT_IDLE_HOURS if HEARTBEAT_ENABLED else None,
            "cached_conversations": cached_conversations,
            "pinned_conversations": pinned_conversations,
        }
    }


@app.get("/")
async def root():

    return {
        "name": "IF Prototype A1 - Agent API",
        "version": "0.1.0",
        "description": "OpenAI-compatible API with intelligent routing to OpenRouter presets",
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions",
            "health": "/health",
            "files": "/files/sandbox/{filepath}",
            "webhooks": "/v1/webhooks/",
        }
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True
    )
