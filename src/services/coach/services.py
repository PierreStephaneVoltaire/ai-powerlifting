from dataclasses import dataclass
from typing import Any

import httpx

from . import principal
from .config import Settings


class ServiceError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Powerlifting service returned {status}: {detail}")


@dataclass(frozen=True)
class Scope:
    person: str
    athlete: str


class PowerliftingServices:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    def _headers(self, scope: Scope, operation: str, turn_id: str = "") -> dict[str, str]:
        headers = {
            "X-Internal-Token": self.settings.internal_token,
            "X-Athlete-Pk": scope.athlete,
            "X-Person-Pk": scope.person,
            "X-PL-Principal": principal.sign(self.settings.principal_secret, scope.person, scope.athlete, operation),
        }
        if turn_id:
            headers["X-IF-Turn-Id"] = turn_id
        return headers

    async def _post(self, url: str, body: dict[str, Any], headers: dict[str, str], timeout: float = 60) -> Any:
        async with self._client(timeout) as client:
            response = await client.post(url, json=body, headers=headers)
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ServiceError(response.status_code, detail)
        return response.json()

    async def access(self, scope: Scope, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        headers = self._headers(scope, operation)
        return await self._post(self.settings.profile_url.rstrip("/") + "/internal/access", {"operation": operation, "arguments": arguments}, {"X-Internal-Token": headers["X-Internal-Token"], "X-PL-Principal": headers["X-PL-Principal"]}, timeout=10)

    async def call(self, scope: Scope, domain: str, operation: str, arguments: dict[str, Any], turn_id: str = "", generation: dict[str, Any] | None = None) -> Any:
        headers = self._headers(scope, operation, turn_id)
        if generation:
            headers["X-IF-Generation-Id"] = str(generation["generation_id"])
            headers["X-IF-Generation-Attempt"] = str(generation["generation_attempt"])
        return await self._post(f"{self.settings.service_url(domain)}/operations/{operation}", arguments, headers)

    async def resume(self, scope: Scope, domain: str, execution_id: str, turn_id: str, challenge_id: str | None = None, content: Any = None) -> Any:
        body = {"challenge_id": challenge_id, "content": content} if challenge_id else {}
        return await self._post(f"{self.settings.service_url(domain)}/executions/{execution_id}", body, self._headers(scope, "domain_resume", turn_id))
