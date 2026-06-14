"""OpenCode execution: POST every job to the Fission function pod.

The IF agent API no longer spawns `opencode` in-process. Every call to
`run_opencode` is forwarded to the Fission router which runs the same
`opencode` invocation inside the Fission function pod (see
`utils/opencode-runner/`). The Fission pod and the API pod share the
same PVCs so the runner can read history.md, write plan.md / response.md,
append to status.log, and see the session-marker file the agent uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .opencode_fission import run_opencode_via_fission


@dataclass
class OpencodeResult:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False


async def run_opencode(
    *,
    agent: str,
    model: str,
    session_dir: Path,
    prompt: str,
    run_id: str | None = None,
    files: list[Path] | None = None,
    timeout: int | None = None,
    # Accepted for caller compatibility; not used by the Fission path.
    continue_session: bool = False,
    status_file: Path | None = None,
    status_callback: Any = None,
    config_path: Path | None = None,
    config_content: str | None = None,
    session_marker_path: Path | None = None,
    cancel_event: Any = None,
) -> OpencodeResult:
    returncode, stdout, stderr = await run_opencode_via_fission(
        job_id=run_id or f"opencode-{agent}",
        agent=agent,
        model=model,
        session_dir=session_dir,
        prompt=prompt,
        files=files,
        timeout=timeout,
    )
    return OpencodeResult(returncode=returncode, stdout=stdout, stderr=stderr)
