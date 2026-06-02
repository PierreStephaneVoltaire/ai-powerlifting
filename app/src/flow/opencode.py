
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from config import OPENCODE_BIN, OPENCODE_TIMEOUT_SECONDS, OPENCODE_CANCEL_GRACE_SECONDS, PROJECT_ROOT

logger = logging.getLogger(__name__)

class RunCancelledError(Exception):
    pass

@dataclass
class OpencodeResult:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False

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

async def _record_run_lifecycle(run_id: str, event: str, **kwargs: Any) -> None:
    try:
        from channels.execution_store import get_execution_store
        store = get_execution_store()
        await store.update_run_record_status(run_id=run_id, event=event, **kwargs)
    except Exception as exc:
        logger.debug("Run record lifecycle update failed for %s: %s", run_id, exc)

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
    run_id: str | None = None,
    config_path: Path | None = None,
    session_marker_path: Path | None = None,
    cancel_event: asyncio.Event | None = None,
) -> OpencodeResult:
    session_dir.mkdir(parents=True, exist_ok=True)
    _prepare_opencode_project(session_dir)
    state_dir = session_dir / ".if"
    state_dir.mkdir(parents=True, exist_ok=True)
    if session_marker_path is not None:
        session_marker = session_marker_path
    else:
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
        logger.info("[opencode] Running agent=%s model=%s dir=%s continue=%s run_id=%s", agent, model, session_dir, use_continue, run_id or "-")
        env = os.environ.copy()
        if config_path is not None:
            env["OPENCODE_CONFIG"] = str(config_path)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(session_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        local_cancel: asyncio.Event | None = None
        if run_id:
            from channels.cancellable_executor import register as _register_run
            local_cancel = _register_run(run_id, proc, cancel_event=cancel_event)
        elif cancel_event is not None:
            local_cancel = cancel_event
        monitor_task = None
        if status_file is not None and status_callback is not None:
            monitor_task = asyncio.create_task(_monitor_status_file(status_file, status_callback, proc))
        try:
            stdout_b, stderr_b = await _wait_for_process(
                proc,
                timeout or OPENCODE_TIMEOUT_SECONDS,
                cancel_event=local_cancel,
                run_id=run_id,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            if run_id:
                from channels.cancellable_executor import deregister as _deregister_run
                _deregister_run(run_id)
                await _record_run_lifecycle(run_id, "timed_out", returncode=-1)
            raise TimeoutError(f"opencode {agent} timed out after {timeout or OPENCODE_TIMEOUT_SECONDS}s")
        except RunCancelledError:
            if monitor_task is not None:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            if run_id:
                from channels.cancellable_executor import deregister as _deregister_run
                _deregister_run(run_id)
                await _record_run_lifecycle(run_id, "cancelled", returncode=-1)
            raise
        finally:
            if monitor_task is not None:
                await asyncio.sleep(0.2)
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            if run_id:
                from channels.cancellable_executor import deregister as _deregister_run
                _deregister_run(run_id)

        result = OpencodeResult(
            returncode=proc.returncode,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )
        if result.returncode != 0:
            logger.warning("[opencode] agent=%s failed rc=%s stderr=%s", agent, result.returncode, result.stderr[:1000])
        return result

    if run_id:
        await _record_run_lifecycle(run_id, "running")

    use_continue = continue_session and session_marker.exists()
    result = await _run(use_continue)
    if result.returncode != 0 and use_continue:
        logger.warning("[opencode] Continue failed for %s; discarding session marker and retrying fresh", agent)
        session_marker.unlink(missing_ok=True)
        result = await _run(False)
    if result.returncode == 0 and continue_session:
        session_marker.write_text("present\n", encoding="utf-8")

    if run_id:
        if result.returncode == 0:
            await _record_run_lifecycle(run_id, "completed", returncode=0)
        else:
            await _record_run_lifecycle(run_id, "failed", returncode=result.returncode, error=result.stderr[:2000] if result.stderr else None)

    return result

async def _wait_for_process(
    proc: asyncio.subprocess.Process,
    timeout: int,
    cancel_event: asyncio.Event | None = None,
    run_id: str | None = None,
) -> tuple[bytes, bytes]:
    communicate_task = asyncio.ensure_future(proc.communicate())
    cancel_wait_task = None
    try:
        if cancel_event is not None:
            async def _wait_cancel():
                while not cancel_event.is_set():
                    await asyncio.sleep(0.5)
            cancel_wait_task = asyncio.ensure_future(_wait_cancel())

        pending = {communicate_task}
        if cancel_wait_task is not None:
            pending.add(cancel_wait_task)

        done, still_pending = await asyncio.wait(
            pending,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_wait_task is not None and cancel_wait_task in done:
            logger.info("Cancel detected for run %s, terminating process", run_id or "?")
            if run_id:
                await _record_run_lifecycle(run_id, "cancel_requested")
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=OPENCODE_CANCEL_GRACE_SECONDS)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass
            if not communicate_task.done():
                communicate_task.cancel()
                try:
                    await communicate_task
                except (asyncio.CancelledError, Exception):
                    pass
            raise RunCancelledError(f"Run {run_id or '?'} cancelled")

        if communicate_task in done:
            return communicate_task.result()

        if communicate_task not in done:
            proc.kill()
            await proc.wait()
            communicate_task.cancel()
            try:
                await communicate_task
            except (asyncio.CancelledError, Exception):
                pass
            raise asyncio.TimeoutError()

    except (RunCancelledError, asyncio.TimeoutError):
        raise
    except Exception:
        if not communicate_task.done():
            communicate_task.cancel()
        raise
    finally:
        if cancel_wait_task is not None and not cancel_wait_task.done():
            cancel_wait_task.cancel()
            try:
                await cancel_wait_task
            except asyncio.CancelledError:
                pass

async def _monitor_status_file(
    status_file: Path,
    status_callback: Callable[[str], Awaitable[None]],
    proc: asyncio.subprocess.Process,
) -> None:
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
