from dataclasses import dataclass
import os
from typing import Any

import httpx

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
    principal: str = ''
    capability: str = ''
    job_id: str = ''


class PowerliftingServices:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    async def _headers(self, scope: Scope, operation: str, destination: str, turn_id: str = "") -> dict[str, str]:
        async with self._client(10) as client:
            response = await client.post(os.getenv('PL_SECURITY_URL', 'http://pl-security:8000').rstrip('/') + '/v1/principals', json={
                'principal': scope.principal, 'capability': scope.capability, 'job_id': scope.job_id,
                'athlete': scope.athlete, 'operation': operation, 'destination': destination})
            response.raise_for_status()
            token = response.json()['principal']
        headers = {'X-Athlete-Pk': scope.athlete, 'X-Person-Pk': scope.person, 'X-PL-Principal': token}
        if turn_id:
            headers['X-IF-Turn-Id'] = turn_id
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
        domain = next((domain for domain in self._domains() if operation in domain[1]), None)
        destination = 'pl-' + domain[0] if domain else 'pl-profile'
        headers = await self._headers(scope, operation, destination)
        result = await self._post(os.getenv('PL_SECURITY_URL', 'http://pl-security:8000').rstrip('/') + '/v1/access', {'principal': headers['X-PL-Principal'], 'operation': operation, 'arguments': arguments, 'destination': destination}, {}, timeout=10)
        return result['context']

    def _domains(self):
        import json
        for path in self.settings.operations_dir.glob('*.json'):
            yield path.stem, {item['name'] for item in json.loads(path.read_text())}

    async def job_capability(self, principal_token: str, job_id: str) -> str:
        result = await self._post(os.getenv('PL_SECURITY_URL', 'http://pl-security:8000').rstrip('/') + '/v1/job-capabilities', {'principal': principal_token, 'job_id': job_id}, {}, timeout=10)
        return result['capability']

    async def call(self, scope: Scope, domain: str, operation: str, arguments: dict[str, Any], turn_id: str = "", generation: dict[str, Any] | None = None) -> Any:
        headers = await self._headers(scope, operation, 'pl-' + domain, turn_id)
        if generation:
            headers["X-IF-Generation-Id"] = str(generation["generation_id"])
            headers["X-IF-Generation-Attempt"] = str(generation["generation_attempt"])
        return await self._post(f"{self.settings.service_url(domain)}/operations/{operation}", arguments, headers)

    async def resume(self, scope: Scope, domain: str, execution_id: str, turn_id: str, challenge_id: str | None = None, content: Any = None) -> Any:
        body = {"challenge_id": challenge_id, "content": content} if challenge_id else {}
        return await self._post(f"{self.settings.service_url(domain)}/executions/{execution_id}", body, await self._headers(scope, "domain_resume", 'pl-' + domain, turn_id))
