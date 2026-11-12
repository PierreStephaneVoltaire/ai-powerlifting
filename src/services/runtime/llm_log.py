import json
import logging
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_context: ContextVar[dict[str, Any]] = ContextVar("llm_log_context", default={})
_logger = logging.getLogger("llm")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


@contextmanager
def scope(**fields: Any) -> Iterator[None]:
    token = _context.set({**_context.get(), **{key: value for key, value in fields.items() if value is not None}})
    try:
        yield
    finally:
        _context.reset(token)


def context() -> dict[str, Any]:
    return dict(_context.get())


def emit(event: str, **fields: Any) -> None:
    record = {"event": event, "ts": time.time(), **_context.get(), **{key: value for key, value in fields.items() if value is not None}}
    _logger.info(json.dumps(record, default=str, ensure_ascii=False))


def usage_fields(usage: Any) -> dict[str, Any]:
    total = getattr(usage, "total", None)
    if total is None:
        return {}
    return {
        "input_tokens": getattr(total, "input_tokens", None),
        "cached_tokens": getattr(total, "cached_input_tokens", None),
        "cache_write_tokens": getattr(total, "cache_write_input_tokens", None),
        "output_tokens": getattr(total, "output_tokens", None),
        "reasoning_tokens": getattr(total, "reasoning_output_tokens", None),
    }
