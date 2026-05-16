import json
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse
from typing import Dict, Any

from mcp_runtime import get_mcp_manager

router = APIRouter(tags=["health_stats"])

@router.get("/api/health/stats/diagnostic")
async def diagnostic():
    return {"status": "ok", "message": "Health stats router is mounted"}

@router.get("/api/health/stats/categories")
async def get_categories():
    try:
        registry = get_mcp_manager()
        result = await registry.call_tool("powerlifting_filter_categories", {})
        if result.startswith("ERROR:"):
            if "Dataset not ready" in result:
                return JSONResponse(
                    status_code=503,
                    content={"detail": result},
                    headers={"Retry-After": "30"},
                )
            status_code = 404 if "Dataset missing" in result else 400
            raise HTTPException(status_code=status_code, detail=result)
        return json.loads(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/health/stats/analyze")
async def analyze_powerlifting(data: Dict[str, Any] = Body(...)):
    try:
        registry = get_mcp_manager()

        args = {
            "squat_kg": data.get("squat"),
            "bench_kg": data.get("bench"),
            "deadlift_kg": data.get("deadlift"),
            "bodyweight_kg": data.get("bodyweight"),
            "sex_code": data.get("sex_code"),
            "federation": data.get("federation"),
            "country": data.get("country"),
            "region": data.get("region"),
            "equipment": data.get("equipment"),
            "sex": data.get("sex"),
            "age_class": data.get("age_class"),
            "year": data.get("year"),
            "event_type": data.get("event_type"),
            "min_dots": data.get("min_dots"),
        }

        result = await registry.call_tool("analyze_powerlifting_stats", args)
        if result.startswith("ERROR:"):
            if "Dataset not ready" in result:
                return JSONResponse(
                    status_code=503,
                    content={"detail": result},
                    headers={"Retry-After": "30"},
                )
            status_code = 404 if "Dataset missing" in result else 400
            raise HTTPException(status_code=status_code, detail=result)
        return json.loads(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
