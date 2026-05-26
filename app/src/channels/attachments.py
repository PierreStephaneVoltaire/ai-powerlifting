import logging
import httpx
from pathlib import Path
from typing import List, Dict, Any
from app_sandbox.local import get_local_sandbox

logger = logging.getLogger(__name__)

# These are still used by the dispatcher for spreadsheet-specific import nudges.
ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
}
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

async def download_discord_attachments(
    attachments: List[Dict[str, Any]],
    conversation_id: str,
    target_uploads_dir: Path | None = None,
) -> List[Dict[str, Any]]:
    """Download each attachment URL into the per-conversation sandbox uploads dir.
    Returns updated attachments list with a `local_path` key added to each.
    """
    if not attachments:
        return []

    try:
        if target_uploads_dir is not None:
            uploads_dir = target_uploads_dir
        else:
            sandbox = get_local_sandbox()
            workdir = Path(sandbox.get_working_dir(conversation_id))
            uploads_dir = workdir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"[Attachments] Failed to resolve sandbox for {conversation_id}: {e}")
        return attachments

    updated_attachments = []
    
    async with httpx.AsyncClient() as client:
        for att in attachments:
            filename = att.get("filename", "unknown_file")
            url = att.get("url")
            if not url:
                updated_attachments.append(att)
                continue
                
            local_path = uploads_dir / filename
            try:
                logger.info(f"[Attachments] Downloading {filename} from {url}")
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                
                local_path.write_bytes(response.content)
                logger.info(f"[Attachments] Downloaded to {local_path}")
                
                # Add local_path to attachment record
                updated_att = dict(att)
                updated_att["local_path"] = str(local_path)
                updated_att["size_kb"] = len(response.content) // 1024
                updated_attachments.append(updated_att)
            except Exception as e:
                logger.error(f"[Attachments] Failed to download {filename}: {e}")
                updated_attachments.append(att)
                
    return updated_attachments
