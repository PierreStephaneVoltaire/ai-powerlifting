import asyncio
import time
from typing import Any

from .catalog import Operation
from .inference import answer_challenge
from .model import Model, ModelError
from .services import PowerliftingServices, Scope


DEADLINE_SECONDS = 900
POLL_SECONDS = 0.5


async def run_operation(services: PowerliftingServices, model: Model, scope: Scope, operation: Operation, arguments: dict[str, Any], turn_id: str, generation: dict[str, Any] | None = None) -> Any:
    if not operation.uses_inference:
        return await services.call(scope, operation.domain, operation.name, arguments)
    result = await services.call(scope, operation.domain, operation.name, arguments, turn_id, generation)
    deadline = time.monotonic() + DEADLINE_SECONDS
    while isinstance(result, dict) and result.get("status") in {"needs_inference", "running"}:
        if time.monotonic() > deadline:
            raise ModelError("uncertain", f"{operation.name} did not finish in time; check its result before retrying")
        if result["status"] == "needs_inference":
            content = await answer_challenge(model, result)
            result = await services.resume(scope, operation.domain, result["execution_id"], turn_id, result["challenge_id"], content)
        else:
            await asyncio.sleep(POLL_SECONDS)
            result = await services.resume(scope, operation.domain, result["execution_id"], turn_id)
    if isinstance(result, dict) and result.get("status") == "succeeded" and "result" in result:
        return result["result"]
    return result
