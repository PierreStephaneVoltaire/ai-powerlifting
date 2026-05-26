"""Async opencode subprocess runner."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from config import OPENCODE_BIN, OPENCODE_TIMEOUT_SECONDS, PROJECT_ROOT

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


def _opencode_model_id(model: str) -> str:
    cleaned = model.strip()
    if cleaned.count("/") == 1:
        return f"openrouter/{cleaned}"
    return cleaned


def _prepare_opencode_project(session_dir: Path) -> None:
    source = PROJECT_ROOT / ".opencode" / "agent"
    if not source.exists():
        return

    target_parent = session_dir / ".opencode"
    target_parent.mkdir(parents=True, exist_ok=True)
    target = target_parent / "agent"
    if target.is_symlink() and not target.exists():
        target.unlink()
    if target.exists():
        if target.is_dir() and not target.is_symlink():
            shutil.copytree(source, target, dirs_exist_ok=True)
        return
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError:
        shutil.copytree(source, target, dirs_exist_ok=True)


async def run_opencode(
    *,
    agent: str,
    model: str,
    session_dir: Path,
    prompt: str,
    timeout: int | None = None,
    continue_session: bool = False,
    status_file: Path | None = None,
    status_callback: Callable[[str], Awaitable[None]] | None = None,
    files: list[Path] | None = None,
) -> OpencodeResult:
    session_dir.mkdir(parents=True, exist_ok=True)
    _prepare_opencode_project(session_dir)
    state_dir = session_dir / ".if"
    state_dir.mkdir(parents=True, exist_ok=True)
    session_marker = state_dir / f"opencode-{agent}.session"

    async def _run(use_continue: bool) -> OpencodeResult:
        cmd = [
            resolve_opencode_bin(),
            "run",
            "--agent",
            agent,
            "--model",
            _opencode_model_id(model),
            "--dangerously-skip-permissions",
            "--dir",
            str(session_dir),
        ]
        if use_continue:
            cmd.append("--continue")
        for file_path in files or []:
            cmd.extend(["--file", str(file_path)])
        cmd.append(prompt)
        logger.info("[opencode] Running agent=%s model=%s dir=%s continue=%s", agent, model, session_dir, use_continue)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(session_dir),
            env=os.environ.copy(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        monitor_task = None
        if status_file is not None and status_callback is not None:
            monitor_task = asyncio.create_task(_monitor_status_file(status_file, status_callback, proc))
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or OPENCODE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"opencode {agent} timed out after {timeout or OPENCODE_TIMEOUT_SECONDS}s")
        finally:
            if monitor_task is not None:
                await asyncio.sleep(0.2)
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

        result = OpencodeResult(
            returncode=proc.returncode,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )
        if result.returncode != 0:
            logger.warning("[opencode] agent=%s failed rc=%s stderr=%s", agent, result.returncode, result.stderr[:1000])
        return result

    use_continue = continue_session and session_marker.exists()
    result = await _run(use_continue)
    if result.returncode != 0 and use_continue:
        logger.warning("[opencode] Continue failed for %s; discarding session marker and retrying fresh", agent)
        session_marker.unlink(missing_ok=True)
        result = await _run(False)
    if result.returncode == 0 and continue_session:
        session_marker.write_text("present\n", encoding="utf-8")
    return result


async def _monitor_status_file(
    status_file: Path,
    status_callback: Callable[[str], Awaitable[None]],
    proc: asyncio.subprocess.Process,
) -> None:
    """Tail a status file and forward new lines while opencode runs."""
    seen = 0
    while proc.returncode is None:
        if status_file.exists():
            text = status_file.read_text(encoding="utf-8", errors="replace")
            if len(text) > seen:
                chunk = text[seen:]
                seen = len(text)
                for line in chunk.splitlines():
                    line = line.strip()
                    if line:
                        await status_callback(line[:900])
        await asyncio.sleep(1.0)
