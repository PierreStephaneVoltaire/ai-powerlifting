"""Directive management API endpoints.

Provides REST API for directive management:
- POST /v1/directives/reload - Reload directives from DynamoDB
- GET /v1/directives - List all active directives
- GET /v1/directives/{alpha}/{beta} - Get a specific directive
- GET /v1/directives/{alpha}/{beta}/history - Get version history
- POST /v1/directives - Create a new directive
- PUT /v1/directives/{alpha}/{beta} - Revise a directive (new version)
- PUT /v1/directives/{alpha}/{beta}/reorder - Change alpha/beta numbers
- DELETE /v1/directives/{alpha}/{beta} - Deactivate a directive
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage.factory import get_directive_store

router = APIRouter(prefix="/v1/directives", tags=["directives"])


# ─── Request models ─────────────────────────────────────────────────────────

class CreateDirectiveRequest(BaseModel):
    """Request body for creating a new directive."""
    alpha: int = Field(..., ge=0, le=5, description="Priority tier (0-5)")
    label: str = Field(..., min_length=1, description="Directive label (UPPER_SNAKE_CASE)")
    content: str = Field(..., min_length=1, description="Full directive text")
    types: List[str] = Field(default=["core"], description="Domain types (e.g., [\"core\", \"code\"])")
    created_by: str = Field(default="operator", description="Who created this directive")


class ReviseDirectiveRequest(BaseModel):
    """Request body for revising an existing directive."""
    content: str = Field(..., min_length=1, description="New content for the directive")
    label: Optional[str] = Field(default=None, description="New label (optional, defaults to existing)")
    types: Optional[List[str]] = Field(default=None, description="New types (optional, defaults to existing)")
    created_by: str = Field(default="operator", description="Who is making this revision")


class ReorderDirectiveRequest(BaseModel):
    """Request body for changing a directive's alpha/beta numbers."""
    new_alpha: int = Field(..., ge=0, le=5, description="New alpha tier")
    new_beta: int = Field(..., ge=1, description="New beta number")


# ─── Helper ─────────────────────────────────────────────────────────────────

def _directive_to_dict(d) -> dict:
    """Convert a Directive to a API response dict, including types."""
    return {
        "alpha": d.alpha,
        "beta": d.beta,
        "version": d.version,
        "label": d.label,
        "content": d.content,
        "types": d.types,
        "created_by": d.created_by,
        "created_at": d.created_at,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/reload")
async def reload_directives():
    """Reload directives from DynamoDB.
    
    Forces a reload of all directives from DynamoDB cache.
    Useful after manual DynamoDB edits.
    
    Returns:
        Dict with status and count of active directives
    """
    try:
        store = get_directive_store()
        directives = store.load()
        return {
            "status": "reloaded",
            "active_count": len(directives)
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )


@router.get("/")
async def list_directives(alpha: int = None):
    """List all active directives.
    
    Args:
        alpha: Optional alpha tier filter (0-5)
    
    Returns:
        Dict with list of active directives
    """
    try:
        store = get_directive_store()
        directives = store.get_all(alpha=alpha)
        return {
            "directives": [_directive_to_dict(d) for d in directives]
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )


@router.post("/")
async def create_directive(req: CreateDirectiveRequest):
    """Create a new directive.
    
    Auto-assigns the next available beta number for the given alpha tier.
    
    Returns:
        The created directive with assigned beta
    """
    try:
        store = get_directive_store()
        directive = store.add(
            alpha=req.alpha,
            label=req.label,
            content=req.content,
            types=req.types,
            created_by=req.created_by,
        )
        return _directive_to_dict(directive)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create directive: {str(e)}"
        )


@router.get("/{alpha}/{beta}")
async def get_directive(alpha: int, beta: int):
    """Get a specific directive.
    
    Args:
        alpha: Alpha tier (0-5)
        beta: Beta number
    
    Returns:
        Dict with directive details
    """
    try:
        store = get_directive_store()
        directive = store.get(alpha, beta)
        
        if not directive:
            raise HTTPException(
                status_code=404,
                detail=f"Directive {alpha}-{beta} not found"
            )
        
        return _directive_to_dict(directive)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )


@router.put("/{alpha}/{beta}")
async def revise_directive(alpha: int, beta: int, req: ReviseDirectiveRequest):
    """Revise an existing directive (creates a new version).
    
    This does NOT modify the existing directive. Instead:
    1. Marks old version as inactive (sets superseded_at)
    2. Creates new version with version = old_version + 1
    
    Args:
        alpha: Alpha tier
        beta: Beta number
    
    Returns:
        The new directive version
    """
    try:
        store = get_directive_store()
        new_directive = store.revise(
            alpha=alpha,
            beta=beta,
            content=req.content,
            types=req.types,
            label=req.label,
            created_by=req.created_by,
        )
        
        if not new_directive:
            raise HTTPException(
                status_code=404,
                detail=f"Directive {alpha}-{beta} not found"
            )
        
        return _directive_to_dict(new_directive)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )


@router.put("/{alpha}/{beta}/reorder")
async def reorder_directive(alpha: int, beta: int, req: ReorderDirectiveRequest):
    """Change a directive's alpha and/or beta numbers.
    
    This deactivates the directive at the old position and creates a new
    one at the new position with version=1.
    
    Args:
        alpha: Current alpha tier
        beta: Current beta number
    
    Returns:
        The new directive at the reordered position
    """
    try:
        store = get_directive_store()
        existing = store.get(alpha, beta)
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Directive {alpha}-{beta} not found"
            )
        
        # Same position — no-op
        if existing.alpha == req.new_alpha and existing.beta == req.new_beta:
            return _directive_to_dict(existing)
        
        # Check if target position is already occupied
        target = store.get(req.new_alpha, req.new_beta)
        if target:
            raise HTTPException(
                status_code=409,
                detail=f"Position {req.new_alpha}-{req.new_beta} is already occupied by {target.label}"
            )
        
        # Deactivate old
        deactivated = store.deactivate(alpha, beta, override=True)
        if not deactivated:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deactivate directive {alpha}-{beta}"
            )
        
        # Create at new position
        new_directive = store.add(
            alpha=req.new_alpha,
            label=existing.label,
            content=existing.content,
            types=existing.types,
            created_by=existing.created_by,
        )
        
        return _directive_to_dict(new_directive)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reorder directive: {str(e)}"
        )


@router.delete("/{alpha}/{beta}")
async def delete_directive(alpha: int, beta: int):
    """Deactivate a directive (soft delete).
    
    Marks the directive as inactive rather than hard deleting,
    preserving audit history.
    
    Args:
        alpha: Alpha tier
        beta: Beta number
    
    Returns:
        Dict with status
    """
    try:
        store = get_directive_store()
        
        # Check exists
        existing = store.get(alpha, beta)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Directive {alpha}-{beta} not found"
            )
        
        deactivated = store.deactivate(alpha, beta, override=True)
        
        if not deactivated:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deactivate directive {alpha}-{beta}"
            )
        
        return {
            "status": "deactivated",
            "alpha": alpha,
            "beta": beta,
            "label": existing.label,
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )


@router.get("/{alpha}/{beta}/history")
async def get_directive_history(alpha: int, beta: int):
    """Get all versions of a directive (audit history).
    
    Returns the complete version history for a directive,
    including superseded versions.
    
    Args:
        alpha: Alpha tier (0-5)
        beta: Beta number
    
    Returns:
        Dict with directive ID and list of all versions
    """
    try:
        store = get_directive_store()
        versions = store.get_history(alpha, beta)
        
        if not versions:
            raise HTTPException(
                status_code=404,
                detail=f"Directive {alpha}-{beta} not found"
            )
        
        return {
            "directive": f"{alpha}-{beta}",
            "versions": [
                {
                    "version": v.version,
                    "label": v.label,
                    "content": v.content,
                    "types": v.types,
                    "active": v.active,
                    "created_by": v.created_by,
                    "created_at": v.created_at,
                    "superseded_at": v.superseded_at,
                }
                for v in versions
            ]
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Directive store not available: {str(e)}"
        )
