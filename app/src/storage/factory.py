
from __future__ import annotations
import logging
from typing import Optional

from config import STORE_BACKEND
from storage.protocol import WebhookStore

logger = logging.getLogger(__name__)

_store: Optional[WebhookStore] = None

def init_store() -> None:

    global _store

    if STORE_BACKEND == "sqlite":
        from storage.sqlite_backend import init_sqlite, SQLiteWebhookStore
        init_sqlite()
        _store = SQLiteWebhookStore()
        logger.info("Storage backend initialized: SQLite")

    elif STORE_BACKEND == "dynamodb":
        raise NotImplementedError(
            "DynamoDB backend not yet implemented. Set STORE_BACKEND=sqlite."
        )

    else:
        raise ValueError(f"Unknown STORE_BACKEND: {STORE_BACKEND}")

def get_webhook_store() -> WebhookStore:

    if _store is None:
        raise RuntimeError("Store not initialized. Call init_store().")
    return _store

def close_store() -> None:

    global _store
    if STORE_BACKEND == "sqlite" and _store is not None:
        from storage.sqlite_backend import close_sqlite
        close_sqlite()
    _store = None
    logger.info("Storage backend closed")

from config import (
    DIRECTIVE_STORE_ENABLED,
    DYNAMODB_DIRECTIVES_TABLE,
    AWS_REGION,
    IF_MODELS_TABLE_NAME,
)

_directive_store = None
_directive_stores_by_pk: dict = {}

def init_directive_store() -> None:





    global _directive_store
    
    if not DIRECTIVE_STORE_ENABLED:
        logger.info("[DirectiveStore] Disabled via DIRECTIVE_STORE_ENABLED=false")
        return
    
    logger.info(f"[DirectiveStore] Initializing with table={DYNAMODB_DIRECTIVES_TABLE}, region={AWS_REGION}")
    
    try:
        from storage.directive_store import DirectiveStore
        
        _directive_store = DirectiveStore(
            table_name=DYNAMODB_DIRECTIVES_TABLE,
            region=AWS_REGION,
            pk="operator",
        )
        _directive_store.load()
        _directive_stores_by_pk["operator"] = _directive_store
        logger.info(
            f"[DirectiveStore] Successfully initialized with {len(_directive_store._cache)} active directives "
            f"from table {DYNAMODB_DIRECTIVES_TABLE}"
        )
    except Exception as e:
        logger.error(f"[DirectiveStore] FAILED to initialize: {type(e).__name__}: {e}")
        logger.error(f"[DirectiveStore] Check AWS credentials, DynamoDB table exists, and network connectivity")
        raise RuntimeError(f"DirectiveStore initialization failed: {e}") from e

def get_directive_store(pk: str = "operator"):

    if pk == "operator":
        if _directive_store is None:
            if not DIRECTIVE_STORE_ENABLED:
                raise RuntimeError(
                    "Directive store is disabled. Set DIRECTIVE_STORE_ENABLED=true."
                )
            raise RuntimeError(
                "Directive store not initialized. Call init_directive_store()."
            )
        return _directive_store
    
    if pk in _directive_stores_by_pk:
        return _directive_stores_by_pk[pk]
    
    if not DIRECTIVE_STORE_ENABLED:
        raise RuntimeError(
            "Directive store is disabled. Set DIRECTIVE_STORE_ENABLED=true."
        )
    
    from storage.directive_store import DirectiveStore
    store = DirectiveStore(
        table_name=DYNAMODB_DIRECTIVES_TABLE,
        region=AWS_REGION,
        pk=pk,
    )
    store.load()
    _directive_stores_by_pk[pk] = store
    logger.info(f"[DirectiveStore] Created store for pk={pk} with {len(store._cache)} active directives")
    return store

_model_registry = None

def init_model_registry() -> None:

    global _model_registry

    try:
        from storage.model_registry import ModelRegistry

        _model_registry = ModelRegistry(
            table_name=IF_MODELS_TABLE_NAME,
            region=AWS_REGION,
        )
        _model_registry.load()
        logger.info(
            f"[ModelRegistry] Initialized with {len(_model_registry._cache)} models "
            f"from table {IF_MODELS_TABLE_NAME}"
        )
    except Exception as e:
        logger.warning(f"[ModelRegistry] Failed to initialize: {type(e).__name__}: {e}")
        _model_registry = None

def get_model_registry():
    if _model_registry is None:
        raise RuntimeError(
            "Model registry not initialized. Call init_model_registry()."
        )
    return _model_registry
