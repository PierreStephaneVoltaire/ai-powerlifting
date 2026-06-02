



from fastapi import APIRouter

from config import API_MODEL_NAME

from .schemas import Model, ModelList

router = APIRouter()

@router.get("/v1/models", response_model=ModelList)
async def list_models():





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




    return await list_models()
