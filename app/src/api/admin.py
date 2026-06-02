
from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/reload-tools")
async def reload_tools(category: Optional[str] = Query(default=None)) -> Dict[str, str]:

    try:
        from mcp_runtime import get_mcp_manager

        statuses = await get_mcp_manager().reload(category)
        logger.info("Tool reload: %s", statuses)
        return statuses
    except Exception as e:
        logger.error(f"Tool reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reload failed: {e}")
