"""Async opencode subprocess runner."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from config import OPENCODE_BIN, OPENCODE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class OpencodeResult:
    returncode: int
    stdout: str
    stderr: str


def resolve_opencode_bin() -> str:
    configured = OPENCODE_BIN.strip()
    if configured:
        return configured
    found = shutil.which("opencode")
    if found:
        return found
    common = Path.home() / ".nvm" / "versions" / "node" / "v24.14.0" / "bin" / "opencode"
    if common.exists():
        return str(common)
    return "opencode"


async def run_opencode(
    *,
    agent: str,
    model: str,
    session_dir: Path,
    prompt: str,
    timeout: int | None = None,
) -> OpencodeResult:
    session_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        resolve_opencode_bin(),
        "run",
        "--agent",
        agent,
        "--model",
        model,
        "--dangerously-skip-permissions",
        "--dir",
        str(session_dir),
        prompt,
    ]
    logger.info("[opencode] Running agent=%s model=%s dir=%s", agent, model, session_dir)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(session_dir),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout or OPENCODE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"opencode {agent} timed out after {timeout or OPENCODE_TIMEOUT_SECONDS}s")

    result = OpencodeResult(
        returncode=proc.returncode,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
    )
    if result.returncode != 0:
        logger.warning("[opencode] agent=%s failed rc=%s stderr=%s", agent, result.returncode, result.stderr[:1000])
    return result

