"""Models endpoint for OpenAI compatibility.

GET /v1/models - Returns available models.
"""
from fastapi import APIRouter

from config import API_MODEL_NAME

from .schemas import Model, ModelList

router = APIRouter()


@router.get("/v1/models", response_model=ModelList)
async def list_models():
    """Return available models for OpenAI compatibility.
    
    Returns a single model 'agent' which triggers the routing pipeline.
    This is the only model the API accepts - all other model values are rejected.
    """
    return ModelList(
        data=[
            Model(
                id=API_MODEL_NAME,
                owned_by="if-prototype"
            )
        ]
    )


@router.get("/api/v1/models", response_model=ModelList)
async def list_models_alias():
    """Alias for /v1/models (OpenWebUI compatibility).
    
    OpenWebUI prefixes API routes with /api, so this provides compatibility.
    """
    return await list_models()
