"""Async client that runs OpenCode jobs on the Fission function pod."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from config import OPENCODE_FISSION_URL, OPENCODE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


async def run_opencode_via_fission(
    *,
    job_id: str,
    agent: str,
    model: str,
    session_dir: Path,
    prompt: str,
    files: list[Path] | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    base_url = OPENCODE_FISSION_URL.rstrip("/")
    payload: dict[str, Any] = {
        "job_id": job_id,
        "agent": agent,
        "model": model,
        "prompt": prompt,
        "session_dir": str(session_dir),
        "files": [str(p) for p in (files or [])],
        "timeout_seconds": int(timeout or OPENCODE_TIMEOUT_SECONDS),
        "extra_env": {},
    }
    timeout_seconds = int(payload["timeout_seconds"])
    http_timeout = float(timeout_seconds) + 60.0
    async with httpx.AsyncClient(timeout=http_timeout) as client:
        resp = await client.post(f"{base_url}/v1/opencode/execute", json=payload)
    data = resp.json()
    status = str(data.get("status") or "error")
    returncode_raw = data.get("returncode")
    if status == "ok":
        returncode = 0 if returncode_raw in (0, None) else int(returncode_raw)
    elif status == "timeout":
        returncode = 124
    else:
        returncode = int(returncode_raw) if returncode_raw is not None else 1
    stdout = str(data.get("stdout") or "")
    stderr = str(data.get("stderr") or "")
    if status != "ok" and not stderr:
        stderr = str(data.get("message") or f"Fission opencode returned status={status}")
    logger.info(
        "[fission-opencode] job=%s agent=%s model=%s returncode=%s",
        job_id, agent, model, returncode,
    )
    return returncode, stdout, stderr
