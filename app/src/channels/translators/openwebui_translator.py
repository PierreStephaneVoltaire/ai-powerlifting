




from __future__ import annotations
from typing import Dict, List, Any

from config import API_MODEL_NAME

def translate_openwebui_batch(
    messages: List[Dict[str, Any]],
    conversation_id: str,
) -> Dict[str, Any]:















    content_parts: List[Dict[str, Any]] = []
    pending_uploads: List[Dict[str, Any]] = []

    for msg in messages:
        text = msg.get("content", "")
        author = msg.get("author", "unknown")
        
        if text:
            content_parts.append({
                "type": "text",
                "text": f"[{author}]: {text}",
            })

        for att in msg.get("attachments", []):
            ct = att.get("content_type", "")
            url = att.get("url", "")
            filename = att.get("filename", "attachment")

            content_parts.append({
                "type": "text",
                "text": f"[Attachment: {filename} — uploads/{filename}]",
            })

            if url:
                pending_uploads.append({
                    "filename": filename,
                    "url": url,
                    "content_type": ct,
                })

    return {
        "model": API_MODEL_NAME,
        "stream": True,
        "messages": [{"role": "user", "content": content_parts}],
        "_conversation_id": conversation_id,
        "_pending_uploads": pending_uploads,
    }
