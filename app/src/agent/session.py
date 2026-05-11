"""Agent session management for OpenHands integration.

This module implements Step 5 of the routing pipeline:
- System prompt assembly (base + memory + preset-specific)
- MCP server resolution
- Agent session creation/reuse
- Message passing to agent via OpenHands SDK
- Response handling and attachment scanning
- Operator context auto-retrieval from user facts
"""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

import httpx
from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation , MessageEvent, TextContent

from config import (
    MEMORY_DB_PATH,
    PERSISTENCE_DIR,
    LLM_API_KEY,
    LLM_BASE_URL,
    PRESET_FALLBACK_MODEL,
    LLM_REASONING_EFFORT,
)
from presets.loader import PresetManager
from agent.prompts.loader import load_prompt
from mcp_servers.config import resolve_mcp_config, get_preset_servers
from agent.memory_tools import get_memory_tools
from agent.tools.user_facts import get_user_facts_tools, set_session_context
from agent.tools.capability_tracker import get_capability_tracker_tools
from agent.tools.opinion_tools import get_opinion_tools
from agent.tools.session_reflection import get_session_reflection_tools
from agent.tools.directive_tools import get_directive_tools
from agent.tools.context_tools import get_context_tools
from agent.tools.subagents import get_subagent_tools
from agent.tools.planfiles import get_planfile_tools
from agent.tools.media_tools import get_media_tools
from agent.tools import file_tools  # registers read_file, write_file, search_files
from agent.tools.discovery_tools import get_discovery_tools
from orchestrator import get_orchestrator_tools, get_analyzer_tools
from app_sandbox import get_local_sandbox


logger = logging.getLogger(__name__)


# Path to pondering addendum file
PONDERING_ADDENDUM_PATH = Path(__file__).parent / "prompts" / "pondering_addendum.md"

# Path to main system prompt (personality/speech patterns)
MAIN_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent / "main_system_prompt.txt"


def load_main_system_prompt() -> str:
    """Load the main system prompt with personality and speech patterns.

    Returns:
        Content of main_system_prompt.txt or empty string if not found
    """
    try:
        if MAIN_SYSTEM_PROMPT_PATH.exists():
            return MAIN_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to load main system prompt: {e}")
    return ""


def load_pondering_addendum() -> str:
    """Load the pondering mode addendum.
    
    Returns:
        Content of pondering_addendum.md or empty string if not found
    """
    try:
        if PONDERING_ADDENDUM_PATH.exists():
            return PONDERING_ADDENDUM_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to load pondering addendum: {e}")
    return ""


@dataclass
class AgentSession:
    """Represents an active agent session."""
    session_id: str
    preset_slug: str
    model: str  # OpenRouter model ID
    system_prompt: str
    mcp_servers: List[str]
    conversation_id: str = ""  # Raw conversation_id (cache_key) for file path resolution
    created_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "preset_slug": self.preset_slug,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "mcp_servers": self.mcp_servers,
            "created_at": self.created_at.isoformat(),
            "message_count": self.message_count,
        }


@dataclass
class AgentResponse:
    """Response from agent execution."""
    content: str
    attachments: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize response to dictionary."""
        return {
            "content": self.content,
            "attachments": self.attachments,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
        }


def resolve_mcp_servers(preset_slug: str) -> List[str]:
    """Resolve MCP servers for a preset.

    Args:
        preset_slug: Preset identifier
        
    Returns:
        List of MCP server keys
    """
    return get_preset_servers(preset_slug)


def get_operator_context(messages: List[Dict[str, Any]], context_id: Optional[str] = None) -> str:
    """Retrieve relevant operator context for system prompt.

    Searches user facts based on the last user message.
    This runs synchronously - LanceDB is local/cloud and fast.

    Args:
        messages: Conversation messages
        context_id: Optional context ID for LanceDB storage

    Returns:
        Formatted operator context block, or empty string if no matches
    """
    from memory.user_facts import (
        FactCategory,
        FactSource,
        get_user_fact_store
    )

    # Extract last user message
    last_user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                last_user_msg = " ".join(text_parts)
            else:
                last_user_msg = content
            break

    if not last_user_msg:
        return ""

    if not context_id:
        logger.debug("No context_id provided, skipping operator context retrieval")
        return ""

    try:
        store = get_user_fact_store()

        # Search for relevant facts
        facts = store.search(context_id, last_user_msg, limit=5)

        # Search for model assessments separately
        assessments = store.search(
            context_id,
            last_user_msg,
            category=FactCategory.MODEL_ASSESSMENT,
            limit=3
        )

        # Deduplicate by ID
        all_facts = {f.id: f for f in facts + assessments}.values()

        if not all_facts:
            return ""

        # Format context block
        lines = ["═══ OPERATOR CONTEXT ═══"]
        for f in all_facts:
            source_tag = "observed" if f.source in (
                FactSource.MODEL_OBSERVED, FactSource.MODEL_ASSESSED
            ) else "stated"
            lines.append(f"- [{f.category.value}] [{source_tag}] {f.content} ({f.updated_at[:10]})")
        lines.append("══════════════════════")
        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to get operator context: {e}")
        return ""


def assemble_system_prompt(
    preset_slug: str,
    memory_context: Optional[str] = None,
    operator_context: Optional[str] = None,
    signals: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[str] = None,
) -> str:
    """Assemble the complete system prompt for a preset.

    Combines:
    1. Current signals block (mental health, life load, training status)
    2. Base system prompt (personality/speech patterns from main_system_prompt.txt)
    3. Operator context block (auto-retrieved from user facts)
    4. Conversation history block (from channel history)
    5. Directives block (from DynamoDB directive store)
    6. Preset-specific instructions (sandbox rules, etc.)

    Args:
        preset_slug: Preset identifier
        memory_context: Optional memory context to inject
        operator_context: Optional operator context from user facts
        signals: Optional signals dict from get_signals() for context injection
        conversation_history: Optional conversation history block

    Returns:
        Complete system prompt string
    """
    # Load the main system prompt (personality/speech patterns)
    base_prompt = load_main_system_prompt()
    if not base_prompt:
        logger.warning("Failed to load main_system_prompt.txt, using fallback")
        base_prompt = "You are a helpful AI assistant."

    # Start with signals if provided (INJECTED FIRST - highest priority context)
    prompt_parts = []
    if signals:
        # Filter out None values for cleaner output
        active_signals = {k: v for k, v in signals.items() if v is not None}
        if active_signals:
            signals_block = f"""<current_signals>
{json.dumps(active_signals, indent=2, default=str)}
</current_signals>"""
            prompt_parts.append(signals_block)
            logger.info(f"[Session] Injected signals into system prompt: score={signals.get('mental_health_score')}, trend={signals.get('trend')}")

    # Add base prompt
    prompt_parts.append(base_prompt)

    # Add operator context if provided (from user facts)
    if operator_context:
        prompt_parts.append(f"\n{operator_context}\n")

    # Add conversation history if provided (from channel history)
    if conversation_history:
        from agent.prompts.loader import render_template
        prompt_parts.append(render_template("conversation_history.j2", history=conversation_history))

    # Add directives block from DirectiveStore
    try:
        from storage.factory import get_directive_store
        store = get_directive_store()
        directives_block = store.format_for_prompt()
        if directives_block:
            directive_count = len(store._cache)
            logger.info(f"[Session] Injecting {directive_count} directives into system prompt for preset '{preset_slug}'")
            prompt_parts.append(f"\n══════════════════════════════════════════\nDIRECTIVES\n══════════════════════════════════════════\n{directives_block}")
        else:
            logger.warning(f"[Session] No directives available for system prompt (preset: '{preset_slug}') - check DirectiveStore initialization")
    except RuntimeError as e:
        # Directive store not initialized or disabled
        logger.warning(f"[Session] Directive store not available for preset '{preset_slug}': {e}")
    except Exception as e:
        logger.error(f"[Session] Failed to get directives for preset '{preset_slug}': {e}")
    
    # Add memory and media protocols from templates
    prompt_parts.append(load_prompt("memory_protocol.j2"))
    prompt_parts.append(load_prompt("media_protocol.j2"))

    # Add memory context if provided
    if memory_context:
        prompt_parts.append(f"\nRELEVANT MEMORIES:\n{memory_context}\n")
    
    # Add preset-specific instructions
    mcp_servers = resolve_mcp_servers(preset_slug)
    
    # Load pondering addendum if active preset is pondering
    if preset_slug == "pondering":
        pondering_addendum = load_pondering_addendum()
        if pondering_addendum:
            logger.info(f"[Session] Loaded pondering addendum ({len(pondering_addendum)} chars)")
            prompt_parts.append(f"\n{pondering_addendum}\n")
    
    # Note: Sandbox MCP server removed in Part6
    return "\n".join(prompt_parts)


def get_model_for_preset(preset_slug: str, preset_manager: PresetManager) -> str:
    """Get the OpenRouter model ID for a preset.

    Args:
        preset_slug: Preset identifier
        preset_manager: Manager with preset data

    Returns:
        OpenRouter model ID
    """
    from models.router import resolve_preset_to_model
    preset = preset_manager.get_preset(preset_slug)
    if not preset:
        return resolve_preset_to_model(PRESET_FALLBACK_MODEL)

    model = preset.model
    if model:
        return resolve_preset_to_model(model)

    return resolve_preset_to_model(PRESET_FALLBACK_MODEL)


async def execute_agent(
    session: AgentSession,
    messages: List[Dict[str, str]],
    http_client: Any,
    stream: bool = False
) -> AgentResponse:
    """Execute agent with messages using OpenHands SDK.
    
    This implementation uses the OpenHands Agent and Conversation classes
    for full MCP server access, tool use, and conversation persistence.
    
    Args:
        session: Agent session configuration
        messages: Conversation messages
        http_client: HTTP client (unused, kept for API compatibility)
        stream: Whether to stream response (not implemented yet)
        
    Returns:
        AgentResponse with content and attachments
    """
    try:
        # Convert the preset model to OpenRouter format
        # The preset.model is like "@preset/architecture", we need "openrouter/@preset/architecture"
        model = session.model
        if not model.startswith("openrouter/"):
            model = f"openrouter/{model}"

        # Look up max_output_tokens from registry using clean model ID
        max_output_tokens = None
        try:
            from storage.factory import get_model_registry
            registry = get_model_registry()
            info = registry.get(session.model)
            if info and info.max_output_tokens:
                max_output_tokens = info.max_output_tokens
        except Exception:
            pass

        # Create OpenHands LLM instance
        llm = LLM(
            usage_id="agent",
            model=model,
            base_url=LLM_BASE_URL,
            api_key=SecretStr(LLM_API_KEY),
            reasoning_effort=LLM_REASONING_EFFORT,
            max_output_tokens=max_output_tokens,
        )
        logger.info(f"Using model: {model}, reasoning_effort: {LLM_REASONING_EFFORT}")
        # Get MCP config for this preset
        mcp_config = resolve_mcp_config(session.preset_slug)
        logger.info(f"Resolved MCP servers: {list(mcp_config.keys())}")
        # Get memory tools
        tools = get_memory_tools()
        # Get user facts tools
        tools.extend(get_user_facts_tools())
        # Get capability tracker tools
        tools.extend(get_capability_tracker_tools())
        # Get opinion tracking tools
        tools.extend(get_opinion_tools())
        # Get session reflection tools
        tools.extend(get_session_reflection_tools())
        # Get directive management tools
        tools.extend(get_directive_tools())
        # Get context tools (date/time, signals, finance snapshot)
        tools.extend(get_context_tools())
        # Get subagent tools (list_specialists, condense_intent, spawn_specialist, deep_think)
        tools.extend(get_subagent_tools(session.conversation_id))
        # Get plan-file tools (shared scratchpad with subagents)
        tools.extend(get_planfile_tools(session.conversation_id))
        # Get media tools (on-demand file/image analysis)
        tools.extend(get_media_tools(session.conversation_id))
        # Create shared HTTP client for orchestrator tools (connection pooling)
        shared_http_client = httpx.AsyncClient(timeout=120.0)
        # Get orchestrator tools (Parts7-9) with shared HTTP client
        tools.extend(get_orchestrator_tools(session.conversation_id, http_client=shared_http_client))
        tools.extend(get_analyzer_tools(session.conversation_id, http_client=shared_http_client))
        # Get discovery tools (discover_tools, use_tool for external plugins)
        tools.extend(get_discovery_tools())
        # Get external tool plugins with scope=main or both
        try:
            from agent.tool_registry import get_tool_registry
            registry = get_tool_registry()
            external_tools = registry.get_sdk_tools(scope="main")
            tools.extend(external_tools)
        except Exception as e:
            logger.debug(f"External tool registry not available: {e}")
        logger.info(f"Loaded {len(tools)} tools: memory, user facts, capability, opinion, reflection, directive, context, delegation, subagent, media, orchestrator, discovery")
        # Create OpenHands Agent
        # Pass the assembled system prompt (which includes directives) to the Agent
        # Use the custom system_prompt.j2 template that renders {{ system_prompt }}
        custom_template_path = Path(__file__).parent / "prompts" / "system_prompt.j2"
        agent = Agent(
            llm=llm,
            tools=tools,
            mcp_config=mcp_config,
            system_prompt_filename=str(custom_template_path),
            system_prompt_kwargs={"system_prompt": session.system_prompt},
        )
        logger.debug("Agent created with system prompt")
        # Create or restore Conversation for persistence
        # OpenHands Conversation expects a UUID object, not a string
        conversation_id_uuid = uuid.uuid4()
        conversation = Conversation(
            agent=agent,
            workspace=get_local_sandbox().get_workspace(session.conversation_id),
            persistence_dir=PERSISTENCE_DIR,
            conversation_id=conversation_id_uuid,
        )
        logger.info(f"Conversation initialized with ID: {session.session_id}")
        # Format messages for the agent
        # OpenHands send_message() only accepts user role — all history is
        # already injected into the system prompt via assemble_system_prompt().
        # Send only the last (current) message.
        if messages:
            last_msg = messages[-1]
            content = last_msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n".join(text_parts)
            conversation.send_message(content)
        
        conversation.run()
        events = conversation.state.events

        # Log tool invocations for observability
        for event in events:
            if hasattr(event, 'tool_call') and event.tool_call:
                tc = event.tool_call
                tool_name = getattr(tc, 'name', getattr(tc, 'function', 'unknown'))
                tool_args = str(getattr(tc, 'arguments', getattr(tc, 'args', {})))[:200]
                logger.info(f"[ToolCall] name={tool_name} | args={tool_args}")

        last_agent_message:MessageEvent = None
        for event in events:
          if isinstance(event, MessageEvent) and event.source == "agent":
            last_agent_message = event
       
        content = ""
        if last_agent_message:
            content = " ".join(
                    c.text
                    for c in last_agent_message.llm_message.content
                    if isinstance(c, TextContent)
                )
        # Scan sandbox for attachments
        attachments = scan_sandbox_for_attachments()
        logger.debug(f"Found attachments: {attachments}")
        return AgentResponse(
            content=content,
            attachments=attachments,
            finish_reason="stop"
        )
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        return AgentResponse(
            content=f"Error executing agent: {str(e)}",
            finish_reason="error"
        )


def scan_sandbox_for_attachments() -> List[str]:
    """Scan sandbox directory for new/modified files.
    
    DEPRECATED (Part6): This function is deprecated.
    
    File attachments are now handled via:
    - FILES: metadata extraction (see src/terminal/files.py)
    - Terminal workspace file serving (see /files/workspace/ endpoint)
    
    This function returns an empty list for backward compatibility.
    The actual file references are extracted from the FILES: line in the
    agent response via strip_files_line() in completions.py.
    
    Returns:
        Empty list (deprecated)
    """
    # Part6: Sandbox scanning deprecated - use FILES: metadata instead
    return []


def create_session_id(conversation_id: str, preset_slug: str) -> str:
    """Create a unique session ID.
    
    Args:
        conversation_id: Conversation identifier
        preset_slug: Preset identifier
        
    Returns:
        Unique session ID
    """
    return f"{conversation_id}-{preset_slug}-{uuid.uuid4().hex[:8]}"


# Session cache (in-memory, no persistence)
_session_cache: Dict[str, AgentSession] = {}


def get_or_create_session(
    conversation_id: str,
    preset_slug: str,
    preset_manager: PresetManager,
    memory_context: Optional[str] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    context_id: Optional[str] = None,
    conversation_history: Optional[str] = None,
    model_override: Optional[str] = None,
) -> AgentSession:
    """Get existing session or create new one.

    Sessions are cached in-memory and keyed by conversation+preset.
    If preset changes, a new session is created.

    Args:
        conversation_id: Conversation identifier
        preset_slug: Preset identifier
        preset_manager: Manager with preset data
        memory_context: Optional memory context
        messages: Optional messages for operator context retrieval
        context_id: Optional context ID for LanceDB storage (format: openwebui_{id} or discord_{id})
        conversation_history: Optional conversation history for system prompt
        model_override: Optional concrete model ID from the router (bypasses preset resolution)

    Returns:
        AgentSession instance
    """
    # Create session key
    session_key = f"{conversation_id}-{preset_slug}"

    # Check cache
    if session_key in _session_cache:
        return _session_cache[session_key]

    # Get operator context from user facts if messages provided
    operator_context = None
    if messages:
        operator_context = get_operator_context(messages, context_id)

    # Get current signals for context injection
    signals = None
    try:
        from agent.tools.context_tools import get_signals_sync
        signals = get_signals_sync()
        logger.debug(f"[Session] Retrieved signals for injection: {signals}")
    except Exception as e:
        logger.warning(f"[Session] Failed to get signals for context injection: {e}")

    # Create new session
    session_id = create_session_id(conversation_id, preset_slug)
    model = model_override if model_override else get_model_for_preset(preset_slug, preset_manager)
    system_prompt = assemble_system_prompt(
        preset_slug,
        memory_context,
        operator_context,
        signals,
        conversation_history=conversation_history,
    )
    mcp_servers = resolve_mcp_servers(preset_slug)

    # Set session context for user facts tools
    # Use context_id if provided, otherwise fall back to conversation_id
    ctx_id = context_id or conversation_id
    set_session_context("operator", conversation_id, ctx_id)
    
    session = AgentSession(
        session_id=session_id,
        conversation_id=conversation_id,
        preset_slug=preset_slug,
        model=model,
        system_prompt=system_prompt,
        mcp_servers=mcp_servers,
    )
    
    # Cache session
    _session_cache[session_key] = session
    
    logger.info(
        f"Created new agent session: {session_id} "
        f"(preset={preset_slug}, model={model}, mcps={mcp_servers})"
    )
    
    return session


def clear_session_cache(conversation_id: Optional[str] = None):
    """Clear session cache.
    
    Args:
        conversation_id: If provided, clear only sessions for this conversation.
                        If None, clear entire cache.
    """
    global _session_cache
    
    if conversation_id:
        # Clear only sessions for this conversation
        keys_to_remove = [
            k for k in _session_cache.keys()
            if k.startswith(f"{conversation_id}-")
        ]
        for key in keys_to_remove:
            del _session_cache[key]
    else:
        # Clear all
        _session_cache.clear()
