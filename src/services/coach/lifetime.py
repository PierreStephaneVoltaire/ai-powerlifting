import asyncio
import logging
from pathlib import Path
from typing import Any

from .config import AISettings, Settings
from .model import workspace_for
from .store import Job


logger = logging.getLogger("coach")
REPORT_FILE = "lifetime_report.md"
NOTE = f"A lifetime training report for this athlete is available as {REPORT_FILE} in the working directory."
MISSING = {"NoSuchKey", "404", "NotFound"}


def _client() -> Any:
    import boto3

    return boto3.client("s3")


def _fetch(bucket: str, athlete: str, client: Any) -> bytes | None:
    from botocore.exceptions import ClientError

    try:
        return client.get_object(Bucket=bucket, Key=f"lifetime/{athlete}/latest.md")["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in MISSING:
            logger.warning("lifetime report fetch failed: %s", exc)
    except Exception as exc:
        logger.warning("lifetime report fetch failed: %s", exc)
    return None


class ReportModel:
    def __init__(self, model: Any, workspace: Path):
        self.model = model
        self.workspace = workspace

    async def complete(self, ai: AISettings, instructions: str, prompt: str) -> str:
        return await self.model.complete(ai, instructions + "\n\n" + NOTE, prompt, workspace=self.workspace)

    async def converse(self, *args: Any, **kwargs: Any) -> Any:
        return await self.model.converse(*args, **kwargs)


async def with_lifetime_report(settings: Settings, model: Any, job: Job, client: Any = None) -> Any:
    if not settings.lifetime_bucket:
        return model
    try:
        body = await asyncio.to_thread(lambda: _fetch(settings.lifetime_bucket, job.athlete, client or _client()))
        if body is None:
            return model
        workspace = workspace_for(settings.workspaces, job.owner, job.job_id)
        (workspace / REPORT_FILE).write_bytes(body)
        return ReportModel(model, workspace)
    except Exception as exc:
        logger.warning("lifetime report unavailable: %s", exc)
        return model
