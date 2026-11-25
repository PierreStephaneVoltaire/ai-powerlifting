import asyncio
import contextvars
import time
import uuid
from dataclasses import dataclass, field


current_execution = contextvars.ContextVar("domain_execution", default=None)


@dataclass
class DomainExecution:
    job_id: str
    athlete: str
    person: str = ""
    operation: str = ""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    future: asyncio.Task | None = None
    error: str | None = None
    deadline: float = field(default_factory=lambda: time.monotonic() + 900)
