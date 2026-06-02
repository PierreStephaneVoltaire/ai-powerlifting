






import json
import logging
from typing import List, Dict, Any, Optional
import httpx

from config import (
    OPENWEBUI_TASK_MARKERS,
    SUGGESTION_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_HEADERS,
)

logger = logging.getLogger(__name__)

class InterceptorResult:

    
    def __init__(
        self,
        is_suggestion_request: bool,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.is_suggestion_request = is_suggestion_request
        self.response = response
        self.error = error
    
    def should_bypass_routing(self) -> bool:

        return self.is_suggestion_request and self.response is not None

def detect_openwebui_task(messages: List[Dict[str, Any]]) -> bool:














    if not messages:
        return False
    
    last_message = messages[-1]
    content = last_message.get("content", "")
    
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = " ".join(text_parts)
    
    if not isinstance(content, str):
        return False
    
    for marker in OPENWEBUI_TASK_MARKERS:
        if marker in content:
            return True
    
    if len(messages) <= 2:
        suggestion_patterns = [
            "suggest",
            "title",
            "follow-up",
            "tags",
            "summarize",
        ]
        content_lower = content.lower()
        if any(pattern in content_lower for pattern in suggestion_patterns):
            if len(content) < 500:
                return True
    
    return False

async def call_suggestion_model(
    messages: List[Dict[str, Any]],
    http_client: httpx.AsyncClient,
    model: str = SUGGESTION_MODEL,
    stream: bool = False
) -> Dict[str, Any]:













    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    
    try:
        response = await http_client.post(
            url,
            headers=OPENROUTER_HEADERS,
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error_detail = e.response.text if e.response else str(e)
        return {
            "error": f"OpenRouter API error: {e.response.status_code}",
            "detail": error_detail
        }
    except Exception as e:
        return {
            "error": "Failed to call suggestion model",
            "detail": str(e)
        }

async def intercept_request(
    messages: List[Dict[str, Any]],
    http_client: httpx.AsyncClient,
    stream: bool = False
) -> InterceptorResult:












    is_task = detect_openwebui_task(messages)
    
    if not is_task:
        return InterceptorResult(is_suggestion_request=False)
    
    logger.info(f"Detected OpenWebUI task, calling {SUGGESTION_MODEL} directly")
    
    response = await call_suggestion_model(
        messages=messages,
        http_client=http_client,
        stream=stream
    )
    
    if "error" in response:
        return InterceptorResult(
            is_suggestion_request=True,
            error=response.get("detail", response.get("error"))
        )
    
    return InterceptorResult(
        is_suggestion_request=True,
        response=response
    )
