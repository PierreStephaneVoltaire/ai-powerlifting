"""Directive management API endpoints.

Provides REST API for directive management:
- POST /v1/directives/reload - Reload directives from DynamoDB
- GET /v1/directives - List all active directives
- GET /v1/directives/{alpha}/{beta} - Get a specific directive
- GET /v1/directives/{alpha}/{beta}/history - Get version history
- POST /v1/directives - Create a new directive
- PUT /v1/directives/{alpha}/{beta} - Revise a directive (new version)
- PUT /v1/directives/{alpha}/{beta}/reorder - Change alpha/beta numbers
- PUT /v1/directives/bulk-reorder - Bulk reorder with collision/swap support
- DELETE /v1/directives/{alpha}/{beta} - Deactivate a directive

All CRUD endpoints accept an optional ``pk`` query parameter (default "operator")
which specifies the DynamoDB partition key to use. The portal backend injects
the user's mapped_pk (or pk fallback) from the if-user table.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage.factory import get_directive_store

router = APIRouter(prefix="/v1/directives", tags=["directives"])


class CreateDirectiveRequest(BaseModel):
    alpha: int = Field(..., ge=0, le=5, description="Priority tier (0-5)")
    label: str = Field(..., min_length=1, description="Directive label")
    content: str = Field(..., min_length=1, description="Full directive text")
    types: List[str] = Field(default=["core"], description="Domain types")
    created_by: str = Field(default="operator", description="Who created this directive")
    global_directive: bool = Field(default=False, description="If True, directive applies to all users (operator-only)")


class ReviseDirectiveRequest(BaseModel):
    content: str = Field(..., min_length=1, description="New content")
    label: Optional[str] = Field(default=None, description="New label")
    types: Optional[List[str]] = Field(default=None, description="New types")
    created_by: str = Field(default="operator", description="Who is making this revision")


class ReorderDirectiveRequest(BaseModel):
    new_alpha: int = Field(..., ge=0, le=5, description="New alpha tier")
    new_beta: int = Field(..., ge=1, description="New beta number")


class BulkReorderItem(BaseModel):
    old_alpha: int = Field(..., ge=0, le=5, description="Current alpha tier")
    old_beta: int = Field(..., ge=1, description="Current beta number")
    new_alpha: int = Field(..., ge=0, le=5, description="Target alpha tier")
    new_beta: int = Field(..., ge=1, description="Target beta number")


class BulkReorderRequest(BaseModel):
    items: List[BulkReorderItem] = Field(..., min_length=1, description="List of directives to reorder")


def _directive_to_dict(d, read_only: bool = False) -> dict:
    return {
        "alpha": d.alpha,
        "beta": d.beta,
        "version": d.version,
        "label": d.label,
        "content": d.content,
        "types": d.types,
        "created_by": d.created_by,
        "created_at": d.created_at,
        "global_directive": d.global_directive,
        "read_only": read_only,
    }


@router.post("/reload")
async def reload_directives():
    try:
        store = get_directive_store()
        directives = store.load()
        return {"status": "reloaded", "active_count": len(directives)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")


@router.get("/")
async def list_directives(alpha: int = None, pk: str = "operator", include_global: bool = False):
    """List directives for the given pk.

    When include_global=True, also fetches global directives from the operator
    store and merges them into the results. Global directives are marked with
    read_only=True when the requesting pk is not "operator".
    """
    try:
        store = get_directive_store(pk=pk)
        directives = store.get_all(alpha=alpha)

        is_operator = (pk == "operator")

        if include_global and not is_operator:
            # Fetch global directives from operator store
            try:
                operator_store = get_directive_store(pk="operator")
                global_directives = operator_store.get_all_global()
                # Filter by alpha if specified
                if alpha is not None:
                    global_directives = [d for d in global_directives if d.alpha == alpha]
                # Build set of user's alpha-beta keys for dedup
                user_keys = {(d.alpha, d.beta) for d in directives}
                # Add global directives that don't conflict with user's own
                for gd in global_directives:
                    if (gd.alpha, gd.beta) not in user_keys:
                        directives.append(gd)
            except RuntimeError:
                pass  # If operator store fails, just return user directives

        # Sort merged list by alpha then beta
        directives.sort(key=lambda d: (d.alpha, d.beta))

        return {"directives": [_directive_to_dict(d, read_only=(d.global_directive and not is_operator)) for d in directives]}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")


@router.post("/")
async def create_directive(req: CreateDirectiveRequest, pk: str = "operator"):
    # Enforce: global_directive=True only allowed for operator
    if req.global_directive and pk != "operator":
        raise HTTPException(status_code=403, detail="Only operator can create global directives")
    try:
        # If global directive, always use operator store regardless of requesting pk
        store_pk = "operator" if req.global_directive else pk
        store = get_directive_store(pk=store_pk)
        directive = store.add(alpha=req.alpha, label=req.label, content=req.content, types=req.types, created_by=req.created_by, global_directive=req.global_directive)
        return _directive_to_dict(directive)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create directive: {str(e)}")


@router.get("/{alpha}/{beta}")
async def get_directive(alpha: int, beta: int, pk: str = "operator"):
    try:
        store = get_directive_store(pk=pk)
        directive = store.get(alpha, beta)
        if not directive:
            raise HTTPException(status_code=404, detail=f"Directive {alpha}-{beta} not found")
        return _directive_to_dict(directive)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")


@router.put("/{alpha}/{beta}")
async def revise_directive(alpha: int, beta: int, req: ReviseDirectiveRequest, pk: str = "operator"):
    try:
        store = get_directive_store(pk=pk)
        new_directive = store.revise(alpha=alpha, beta=beta, content=req.content, types=req.types, label=req.label, created_by=req.created_by)
        if not new_directive:
            raise HTTPException(status_code=404, detail=f"Directive {alpha}-{beta} not found")
        return _directive_to_dict(new_directive)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")


@router.put("/{alpha}/{beta}/reorder")
async def reorder_directive(alpha: int, beta: int, req: ReorderDirectiveRequest, pk: str = "operator"):
    try:
        store = get_directive_store(pk=pk)
        existing = store.get(alpha, beta)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Directive {alpha}-{beta} not found")
        if existing.alpha == req.new_alpha and existing.beta == req.new_beta:
            return _directive_to_dict(existing)
        target = store.get(req.new_alpha, req.new_beta)
        if target:
            raise HTTPException(status_code=409, detail=f"Position {req.new_alpha}-{req.new_beta} is already occupied by {target.label}")
        deactivated = store.deactivate(alpha, beta, override=True)
        if not deactivated:
            raise HTTPException(status_code=500, detail=f"Failed to deactivate directive {alpha}-{beta}")
        new_directive = store.add(alpha=req.new_alpha, label=existing.label, content=existing.content, types=existing.types, created_by=existing.created_by)
        return _directive_to_dict(new_directive)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reorder directive: {str(e)}")


@router.put("/bulk-reorder")
async def bulk_reorder_directives(req: BulkReorderRequest, pk: str = "operator"):
    """Bulk reorder directives with collision/swap support and automatic beta resequencing.

    When two directives swap positions (A → B's slot and B → A's slot),
    both are moved. After all moves, beta numbers within each alpha tier
    are resequenced to be contiguous (1, 2, 3, …).
    """
    try:
        store = get_directive_store(pk=pk)
        items = [i.model_dump() for i in req.items]
        updated = store.bulk_reorder(items)
        return {
            "directives": [_directive_to_dict(d) for d in updated],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk reorder: {str(e)}")


@router.delete("/{alpha}/{beta}")
async def delete_directive(alpha: int, beta: int, pk: str = "operator"):
    try:
        store = get_directive_store(pk=pk)
        existing = store.get(alpha, beta)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Directive {alpha}-{beta} not found")
        deactivated = store.deactivate(alpha, beta, override=True)
        if not deactivated:
            raise HTTPException(status_code=500, detail=f"Failed to deactivate directive {alpha}-{beta}")
        return {"status": "deactivated", "alpha": alpha, "beta": beta, "label": existing.label}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")


@router.get("/{alpha}/{beta}/history")
async def get_directive_history(alpha: int, beta: int, pk: str = "operator"):
    try:
        store = get_directive_store(pk=pk)
        versions = store.get_history(alpha, beta)
        if not versions:
            raise HTTPException(status_code=404, detail=f"Directive {alpha}-{beta} not found")
        return {
            "directive": f"{alpha}-{beta}",
            "versions": [
                {"version": v.version, "label": v.label, "content": v.content, "types": v.types, "active": v.active, "created_by": v.created_by, "created_at": v.created_at, "superseded_at": v.superseded_at}
                for v in versions
            ]
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Directive store not available: {str(e)}")
