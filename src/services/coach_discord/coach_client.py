import asyncio

import httpx


TERMINAL = {"succeeded", "failed", "cancelled", "uncertain"}


class CoachClient:
    def __init__(self, base_url: str, internal_token: str, poll_seconds: float = 1.0, timeout_seconds: float = 840, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=30, transport=self.transport)

    def _headers(self, person: str) -> dict[str, str]:
        return {"X-Internal-Token": self.internal_token, "X-Person-Pk": person}

    async def ask(self, person: str, athlete: str, conversation_id: str, text: str) -> str:
        async with self._client() as client:
            response = await client.post(f"/v1/conversations/{conversation_id}/turns", json={"messages": [{"role": "user", "content": text}], "athlete": athlete}, headers=self._headers(person))
            response.raise_for_status()
            job_id = response.json()["job_id"]
            for _ in range(int(self.timeout_seconds / self.poll_seconds)):
                response = await client.get(f"/v1/jobs/{job_id}/result", headers=self._headers(person))
                response.raise_for_status()
                job = response.json()
                if job["status"] in TERMINAL:
                    if job["status"] != "succeeded":
                        return f"The Coach could not finish ({job['status']}): {(job.get('error') or {}).get('message', 'unknown error')}"
                    return (job.get("result") or {}).get("content") or ""
                await asyncio.sleep(self.poll_seconds)
        return "The Coach is still working; ask again in a moment."

    async def reset(self, person: str, conversation_id: str) -> None:
        async with self._client() as client:
            response = await client.delete(f"/v1/conversations/{conversation_id}", headers=self._headers(person))
            response.raise_for_status()
