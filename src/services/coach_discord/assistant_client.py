import asyncio
import json
from dataclasses import dataclass, field

import httpx


TERMINAL = {"succeeded", "failed", "cancelled", "uncertain"}
DIFF_LIMIT = 1200
SUMMARY_LIMIT = 300


@dataclass
class Answer:
    content: str
    proposals: list[dict] = field(default_factory=list)


def error_text(error) -> str:
    if isinstance(error, dict):
        error = error.get("message")
    return error or "unknown error"


def proposal_message(proposal: dict) -> str:
    proposal_id = proposal["id"]
    diff = proposal.get("diff")
    diff_text = json.dumps(diff, separators=(",", ":"), ensure_ascii=False) if diff not in (None, "", {}) else "(no diff)"
    if len(diff_text) > DIFF_LIMIT:
        diff_text = diff_text[:DIFF_LIMIT] + "..."
    diff_text = diff_text.replace("```", "'''")
    summary = (proposal.get("summary") or proposal.get("operation") or "Proposed change")[:SUMMARY_LIMIT]
    if proposal.get("destructive"):
        target = proposal.get("target_id") or ""
        instructions = f"This change is destructive. Target: `{target}`.\nReply `approve {proposal_id} {target}` to confirm it or `reject {proposal_id}`."
    else:
        instructions = f"Reply `approve {proposal_id}` or `reject {proposal_id}`."
    return f"Proposed change `{proposal_id}`: {summary}\n```json\n{diff_text}\n```\n{instructions}"


class AssistantClient:
    def __init__(self, base_url: str, poll_seconds: float = 1.0, timeout_seconds: float = 840, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=30, transport=self.transport)

    def _headers(self, person: str, athlete: str) -> dict[str, str]:
        return {'X-Person-Pk': person, 'X-Athlete-Pk': athlete}

    async def ask(self, person: str, athlete: str, conversation_id: str, text: str) -> Answer:
        async with self._client() as client:
            response = await client.post(f"/v1/conversations/{conversation_id}/turns", json={"messages": [{"role": "user", "content": text}], "athlete": athlete}, headers=self._headers(person, athlete))
            response.raise_for_status()
            job_id = response.json()["job_id"]
            for _ in range(int(self.timeout_seconds / self.poll_seconds)):
                response = await client.get(f"/v1/jobs/{job_id}/result", headers=self._headers(person, athlete))
                response.raise_for_status()
                job = response.json()
                if job["status"] in TERMINAL:
                    pending = [proposal for proposal in job.get("proposals") or [] if proposal.get("state") == "pending"]
                    content = (job.get("result") or {}).get("content") or ""
                    if job["status"] != "succeeded" and not content:
                        content = f"The assistant could not finish ({job['status']}): {error_text(job.get('error'))}"
                    return Answer(content, pending)
                await asyncio.sleep(self.poll_seconds)
        return Answer("The assistant is still working; ask again in a moment.")

    async def decide(self, person: str, athlete: str, proposal_id: str, approve: bool, target: str | None = None) -> str | None:
        action = "approve" if approve else "reject"
        async with self._client() as client:
            response = await client.post(f"/v1/proposals/{proposal_id}/{action}", json={"target": target} if target else {}, headers=self._headers(person, athlete))
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                try:
                    detail = response.json().get("error") or response.json().get("detail")
                except ValueError:
                    detail = None
                return f"Could not {action} `{proposal_id}`: {detail or response.status_code}"
            state = response.json().get("state", action)
            return f"Proposal `{proposal_id}` is now {state}."
