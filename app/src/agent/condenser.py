









from __future__ import annotations
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from config import (
    CONTEXT_CONDENSE_THRESHOLD,
    MESSAGE_WINDOW,
    OPENROUTER_API_KEY,
    LLM_BASE_URL,
    CONDENSER_MODEL,
    TOKENIZER_MODEL,
)

@dataclass
class CondensationResult:









    original_token_count: int
    condensed_token_count: int
    condensed_messages: List[Dict[str, Any]]
    was_condensed: bool
    summary: Optional[str] = None

def estimate_token_count(messages: List[Dict[str, Any]], model: str = TOKENIZER_MODEL) -> int:












    if not messages:
        return 0
    
    full_text = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        full_text += f"{role}: {content}\n"
    
    if TIKTOKEN_AVAILABLE:
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(full_text))
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(full_text))
    else:
        return len(full_text) // 4

def should_condense(messages: List[Dict[str, Any]]) -> bool:








    token_count = estimate_token_count(messages)
    return token_count > CONTEXT_CONDENSE_THRESHOLD

def extract_recent_messages(
    messages: List[Dict[str, Any]],
    window: int = None
) -> List[Dict[str, Any]]:









    window = window or MESSAGE_WINDOW
    return messages[-window:] if len(messages) > window else messages

def extract_older_messages(
    messages: List[Dict[str, Any]],
    window: int = None
) -> List[Dict[str, Any]]:









    window = window or MESSAGE_WINDOW
    return messages[:-window] if len(messages) > window else []

async def condense_with_openrouter(
    messages: List[Dict[str, Any]],
    http_client: Any,
    model: str = None
) -> str:















    if model is None:
        model = CONDENSER_MODEL
    
    conversation_text = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        conversation_text += f"{role.upper()}: {content}\n\n"
    
    from agent.prompts.loader import load_prompt, render_template
    system_prompt = load_prompt("condenser_system.j2")
    user_prompt = render_template("condenser_user.j2", conversation_text=conversation_text)

    try:
        import httpx
        
        response = await http_client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/if-prototype",
                "X-Title": "IF Prototype A1"
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=30.0
        )
        
        response.raise_for_status()
        data = response.json()
        
        return data["choices"][0]["message"]["content"]
        
    except Exception as e:
        return f"[Condensation failed: {str(e)}]\nConversation had {len(messages)} messages before recent window."

async def condense_conversation(
    messages: List[Dict[str, Any]],
    http_client: Any,
    condensation_model: str = None
) -> CondensationResult:
















    if condensation_model is None:
        condensation_model = CONDENSER_MODEL
    
    original_tokens = estimate_token_count(messages)
    
    if not should_condense(messages):
        return CondensationResult(
            original_token_count=original_tokens,
            condensed_token_count=original_tokens,
            condensed_messages=messages,
            was_condensed=False
        )
    
    recent_messages = extract_recent_messages(messages)
    older_messages = extract_older_messages(messages)
    
    if not older_messages:
        return CondensationResult(
            original_token_count=original_tokens,
            condensed_token_count=original_tokens,
            condensed_messages=messages,
            was_condensed=False
        )
    
    summary = await condense_with_openrouter(
        older_messages,
        http_client,
        condensation_model
    )
    
    condensed_messages = [
        {
            "role": "system",
            "content": f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]\n\nRecent messages follow."
        }
    ] + recent_messages
    
    condensed_tokens = estimate_token_count(condensed_messages)
    
    return CondensationResult(
        original_token_count=original_tokens,
        condensed_token_count=condensed_tokens,
        condensed_messages=condensed_messages,
        was_condensed=True,
        summary=summary
    )

def format_condensed_messages(messages: List[Dict[str, Any]]) -> str:








    output_lines = [f"Condensed conversation ({len(messages)} messages):", ""]
    
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        if len(content) > 100:
            content = content[:100] + "..."
        
        output_lines.append(f"{i}. [{role.upper()}] {content}")
    
    return "\n".join(output_lines)
