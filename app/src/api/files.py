




import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import SANDBOX_PATH, TERMINAL_VOLUME_HOST_ROOT

router = APIRouter()
logger = logging.getLogger(__name__)

def get_sandbox_directory() -> Path:





    sandbox = Path(SANDBOX_PATH)
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox

def get_conversation_sandbox(conversation_id: str) -> Path:








    sandbox = Path(SANDBOX_PATH) / conversation_id
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox

@router.get("/files/sandbox/{conversation_id}/{filepath:path}")
async def serve_sandbox_file(conversation_id: str, filepath: str):















    sandbox_dir = get_conversation_sandbox(conversation_id)
    
    file_path = sandbox_dir / filepath
    
    try:
        file_path = file_path.resolve()
        sandbox_dir = sandbox_dir.resolve()
        
        if not str(file_path).startswith(str(sandbox_dir)):
            raise HTTPException(
                status_code=403,
                detail="Access denied: path traversal denied"
            )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {filepath}"
        )
    
    if not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Not a file: {filepath}"
        )
    
    content_type = get_content_type(file_path.suffix)
    
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=file_path.name
    )

def _hash8(chat_id: str) -> str:








    return hashlib.sha256(chat_id.encode()).hexdigest()[:8]

@router.get("/files/workspace/{chat_id}/{filepath:path}")
async def serve_workspace_file(chat_id: str, filepath: str):















    if not TERMINAL_VOLUME_HOST_ROOT:
        raise HTTPException(
            status_code=501,
            detail="Workspace file serving requires TERMINAL_VOLUME_HOST_ROOT configuration"
        )
    
    normalized = os.path.normpath(filepath)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise HTTPException(
            status_code=403,
            detail="Access denied: path traversal denied"
        )
    
    suffix = _hash8(chat_id)
    volume_name = f"if-ws-{suffix}"
    
    volume_path = Path(TERMINAL_VOLUME_HOST_ROOT) / volume_name / "_data"
    full_path = volume_path / normalized
    
    try:
        full_path = full_path.resolve()
        volume_path = volume_path.resolve()
        
        if not str(full_path).startswith(str(volume_path)):
            raise HTTPException(
                status_code=403,
                detail="Access denied: path escapes volume"
            )
    except Exception as e:
        logger.warning(f"[Workspace] Path resolution error: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )
    
    if not full_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {filepath}"
        )
    
    if not full_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Not a file: {filepath}"
        )
    
    content_type = get_content_type(full_path.suffix)
    
    logger.info(f"[Workspace] Serving file: {full_path} for chat_id: {chat_id}")
    
    return FileResponse(
        path=full_path,
        media_type=content_type,
        filename=full_path.name
    )

def get_content_type(extension: str) -> Optional[str]:








    extension = extension.lower()
    
    content_types = {
        ".py": "text/x-python",
        ".ts": "text/typescript",
        ".js": "text/javascript",
        ".jsx": "text/javascript",
        ".tsx": "text/typescript",
        ".go": "text/x-go",
        ".rs": "text/x-rust",
        ".rb": "text/x-ruby",
        ".java": "text/x-java",
        ".c": "text/x-c",
        ".cpp": "text/x-c++",
        ".cs": "text/x-csharp",
        ".swift": "text/x-swift",
        ".kt": "text/x-kotlin",
        
        ".tf": "text/x-terraform",
        ".hcl": "text/x-hcl",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".json": "application/json",
        ".toml": "text/x-toml",
        ".tfvars": "text/x-terraform",
        
        ".env.example": "text/plain",
        ".ini": "text/x-ini",
        ".cfg": "text/x-config",
        ".conf": "text/plain",
        ".properties": "text/x-java-properties",
        ".xml": "application/xml",
        
        ".sh": "text/x-shellscript",
        ".bash": "text/x-shellscript",
        ".zsh": "text/x-shellscript",
        ".ps1": "text/x-powershell",
        ".bat": "text/x-bat",
        
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".rst": "text/x-rst",
        ".adoc": "text/x-asciidoc",
        
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".drawio": "application/xml",
        
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        
        ".csv": "text/csv",
        ".parquet": "application/octet-stream",
        ".sql": "text/x-sql",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    
    return content_types.get(extension)
