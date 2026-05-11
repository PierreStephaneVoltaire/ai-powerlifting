"""Context condensation for long conversations.

When conversations exceed CONTEXT_CONDENSE_THRESHOLD tokens, they are condensed
before routing and agent processing. This prevents token budget exhaustion on
long-running persistent conversations while preserving:
- Core topic and intent
- Key decisions and outcomes
- Recent messages verbatim (last MESSAGE_WINDOW messages)
- Operator-disclosed personal context (relevant to memory)
"""
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
    """Result of context condensation.
    
    Attributes:
        original_token_count: Token count before condensation
        condensed_token_count: Token count after condensation
        condensed_messages: The condensed message list
        was_condensed: Whether condensation was performed
        summary: Summary of removed content (if any)
    """
    original_token_count: int
    condensed_token_count: int
    condensed_messages: List[Dict[str, Any]]
    was_condensed: bool
    summary: Optional[str] = None


def estimate_token_count(messages: List[Dict[str, Any]], model: str = TOKENIZER_MODEL) -> int:
    """Estimate the token count of a conversation.
    
    Uses tiktoken for accurate token counting. Falls back to character-based
    estimation if tiktoken is not available.
    
    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model: Model to use for tokenization (default: gpt-4)
        
    Returns:
        Estimated token count
    """
    if not messages:
        return 0
    
    # Build the full conversation text
    full_text = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        # Add role tokens (approximate)
        full_text += f"{role}: {content}\n"
    
    if TIKTOKEN_AVAILABLE:
        try:
            # Use cl100k_base encoding (used by GPT-4, GPT-3.5-turbo, etc.)
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(full_text))
        except KeyError:
            # Model not in tiktoken, use cl100k_base as fallback
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(full_text))
    else:
        # Fallback: ~4 characters per token (rough estimate)
        return len(full_text) // 4


def should_condense(messages: List[Dict[str, Any]]) -> bool:
    """Check if a conversation should be condensed.
    
    Args:
        messages: List of message dicts
        
    Returns:
        True if token count exceeds CONTEXT_CONDENSE_THRESHOLD
    """
    token_count = estimate_token_count(messages)
    return token_count > CONTEXT_CONDENSE_THRESHOLD


def extract_recent_messages(
    messages: List[Dict[str, Any]],
    window: int = None
) -> List[Dict[str, Any]]:
    """Extract the most recent N messages.
    
    Args:
        messages: Full message list
        window: Number of messages to extract (default: MESSAGE_WINDOW)
        
    Returns:
        List of the most recent messages
    """
    window = window or MESSAGE_WINDOW
    return messages[-window:] if len(messages) > window else messages


def extract_older_messages(
    messages: List[Dict[str, Any]],
    window: int = None
) -> List[Dict[str, Any]]:
    """Extract messages older than the recent window.
    
    Args:
        messages: Full message list
        window: Number of recent messages to exclude (default: MESSAGE_WINDOW)
        
    Returns:
        List of older messages (excluding recent window)
    """
    window = window or MESSAGE_WINDOW
    return messages[:-window] if len(messages) > window else []


async def condense_with_openrouter(
    messages: List[Dict[str, Any]],
    http_client: Any,
    model: str = None
) -> str:
    """Condense conversation history using OpenRouter.
    
    This creates a summary of the conversation that preserves:
    - Core topic and intent
    - Key decisions and outcomes
    - Operator-disclosed personal context
    
    Args:
        messages: Messages to condense (older messages, not recent window)
        http_client: Async HTTP client for API calls
        model: Model to use for condensation (default: from CONDENSER_MODEL env var)
        
    Returns:
        Condensed summary text
    """
    # Use config default if no model specified
    if model is None:
        model = CONDENSER_MODEL
    
    # Build conversation text for condensation
    conversation_text = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        conversation_text += f"{role.upper()}: {content}\n\n"
    
    # Load prompts from templates
    from agent.prompts.loader import load_prompt, render_template
    system_prompt = load_prompt("condenser_system.j2")
    user_prompt = render_template("condenser_user.j2", conversation_text=conversation_text)

    # Call OpenRouter API
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
        # If condensation fails, return a basic summary
        return f"[Condensation failed: {str(e)}]\nConversation had {len(messages)} messages before recent window."


async def condense_conversation(
    messages: List[Dict[str, Any]],
    http_client: Any,
    condensation_model: str = None
) -> CondensationResult:
    """Condense a conversation if it exceeds the token threshold.
    
    This is the main entry point for context condensation. It:
    1. Estimates token count
    2. Checks if condensation is needed
    3. If yes, condenses older messages and appends recent window
    4. Returns the result
    
    Args:
        messages: Full message list
        http_client: Async HTTP client for API calls
        condensation_model: Model to use for condensation (default: from CONDENSER_MODEL env var)
        
    Returns:
        CondensationResult with condensed messages
    """
    # Use config default if no model specified
    if condensation_model is None:
        condensation_model = CONDENSER_MODEL
    
    # Estimate original token count
    original_tokens = estimate_token_count(messages)
    
    # Check if condensation is needed
    if not should_condense(messages):
        return CondensationResult(
            original_token_count=original_tokens,
            condensed_token_count=original_tokens,
            condensed_messages=messages,
            was_condensed=False
        )
    
    # Extract recent and older messages
    recent_messages = extract_recent_messages(messages)
    older_messages = extract_older_messages(messages)
    
    if not older_messages:
        # No older messages to condense
        return CondensationResult(
            original_token_count=original_tokens,
            condensed_token_count=original_tokens,
            condensed_messages=messages,
            was_condensed=False
        )
    
    # Condense older messages
    summary = await condense_with_openrouter(
        older_messages,
        http_client,
        condensation_model
    )
    
    # Create condensed message list
    # The summary becomes a system message at the start
    condensed_messages = [
        {
            "role": "system",
            "content": f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]\n\nRecent messages follow."
        }
    ] + recent_messages
    
    # Estimate new token count
    condensed_tokens = estimate_token_count(condensed_messages)
    
    return CondensationResult(
        original_token_count=original_tokens,
        condensed_token_count=condensed_tokens,
        condensed_messages=condensed_messages,
        was_condensed=True,
        summary=summary
    )


def format_condensed_messages(messages: List[Dict[str, Any]]) -> str:
    """Format condensed messages for display/debugging.
    
    Args:
        messages: Condensed message list
        
    Returns:
        Formatted string representation
    """
    output_lines = [f"Condensed conversation ({len(messages)} messages):", ""]
    
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        # Truncate long content for display
        if len(content) > 100:
            content = content[:100] + "..."
        
        output_lines.append(f"{i}. [{role.upper()}] {content}")
    
    return "\n".join(output_lines)
