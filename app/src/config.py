"""Configuration module for IF Prototype A1.

Loads environment variables and defines constants for the API server.
"""
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()




OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is required")

LLM_API_KEY = os.getenv("LLM_API_KEY", OPENROUTER_API_KEY)  # Default to OPENROUTER_API_KEY



# LLM Configuration
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

# Routing Configuration
MESSAGE_WINDOW = int(os.getenv("MESSAGE_WINDOW", "8"))
CRISIS_THRESHOLD = float(os.getenv("CRISIS_THRESHOLD", "0.3"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
CONFIDENCE_GAP = float(os.getenv("CONFIDENCE_GAP", "0.2"))
RECLASSIFY_MESSAGE_COUNT = int(os.getenv("RECLASSIFY_MESSAGE_COUNT", "4"))

# Model Configuration
SUGGESTION_MODEL = os.getenv("SUGGESTION_MODEL", "mistralai/mistral-nemo")

# Parse comma-separated scoring models
SCORING_MODELS_STR = os.getenv(
    "SCORING_MODELS",
    "google/gemini-2.5-flash-lite,qwen/qwen3-32b,z-ai/glm-4.7-flash"
)
SCORING_MODELS: List[str] = [
    model.strip() for model in SCORING_MODELS_STR.split(",") if model.strip()
]

# Google Sheets MCP server
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "")

# Yahoo Finance (no API key required)
# Uses mcp-yahoo-finance package directly

# Alpha Vantage API key for stock data
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")

# Paths
SANDBOX_PATH = os.getenv("SANDBOX_PATH", "./sandbox")
MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "./data/memory_db")
PERSISTENCE_DIR = os.getenv("PERSISTENCE_DIR", "./data/conversations")

# LanceDB Configuration (for user facts storage)
FACTS_BASE_PATH = os.getenv("FACTS_BASE_PATH", "./data/facts")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Storage Configuration (Phase 2)
STORAGE_DB_PATH = os.getenv("STORAGE_DB_PATH", "./data/store.db")
STORE_BACKEND = os.getenv("STORE_BACKEND", "sqlite")
# Future DynamoDB vars:
# DYNAMODB_WEBHOOK_TABLE = os.getenv("DYNAMODB_WEBHOOK_TABLE", "")
# AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Topic Shift Detection (Phase 1)
TOPIC_SHIFT_MODEL = os.getenv("TOPIC_SHIFT_MODEL", "z-ai/glm-4.7-flash")

# Context Condensation
CONTEXT_CONDENSE_THRESHOLD = int(os.getenv("CONTEXT_CONDENSE_THRESHOLD", "250000"))

# Maximum characters for tool output before OpenHands SDK truncates it.
# Default SDK value is 50000 which silently clips large tool results
# (e.g. health_get_program ~95K) causing hallucinations from incomplete data.
TOOL_OUTPUT_CHAR_LIMIT = int(os.getenv("TOOL_OUTPUT_CHAR_LIMIT", "200000"))

# =============================================================================
# Tier System Configuration (Phase 3)
# =============================================================================

# Tier upgrade threshold (fraction of context limit before upgrade)
TIER_UPGRADE_THRESHOLD = float(os.getenv("TIER_UPGRADE_THRESHOLD", "0.65"))

# Context limits per tier (in tokens)
TIER_AIR_LIMIT = int(os.getenv("TIER_AIR_LIMIT", "100000"))
TIER_STANDARD_LIMIT = int(os.getenv("TIER_STANDARD_LIMIT", "200000"))
TIER_HEAVY_LIMIT = int(os.getenv("TIER_HEAVY_LIMIT", "1000000"))

# OpenRouter presets per tier
TIER_AIR_PRESET = os.getenv("TIER_AIR_PRESET", "@preset/air")
TIER_STANDARD_PRESET = os.getenv("TIER_STANDARD_PRESET", "@preset/standard")
TIER_HEAVY_PRESET = os.getenv("TIER_HEAVY_PRESET", "@preset/heavy")

# =============================================================================
# opencode Flow Configuration
# =============================================================================

OPENCODE_BIN = os.getenv("OPENCODE_BIN", "")
OPENCODE_PLANNER_MODEL = os.getenv("OPENCODE_PLANNER_MODEL", "deepseek/deepseek-v4-flash")
OPENCODE_TIMEOUT_SECONDS = int(os.getenv("OPENCODE_TIMEOUT_SECONDS", "900"))
IF_DIRECT_LLM_TOOL_ROUNDS = int(os.getenv("IF_DIRECT_LLM_TOOL_ROUNDS", "8"))
IF_DEFAULT_DIRECT_MODEL = os.getenv("IF_DEFAULT_DIRECT_MODEL", "openai/gpt-5.4-mini")
IF_TECHNICAL_ARTIFACT_EXCLUDES = {
    "history.md",
    "plan.md",
    "review.md",
    "response.md",
}

# MCP tool server categories managed by IF at startup.
MCP_SERVER_CATEGORIES = [
    item.strip()
    for item in os.getenv(
        "MCP_SERVER_CATEGORIES",
        "health,finance,diary,proposals,temporal,supplement_research",
    ).split(",")
    if item.strip()
]

# =============================================================================
# Specialist Subagent Configuration (Phase 4)
# =============================================================================

# Default preset for specialist subagents
SPECIALIST_PRESET = os.getenv("SPECIALIST_PRESET", "general")

# Maximum turns per specialist subagent
SPECIALIST_MAX_TURNS = int(os.getenv("SPECIALIST_MAX_TURNS", "15"))

# Agentic specialist configuration (SDK Conversation.run() loop)
AGENTIC_MAX_ITERATIONS = int(os.getenv("AGENTIC_MAX_ITERATIONS", "25"))

# Deep thinker (pondering) configuration
THINKING_PRESET = os.getenv("THINKING_PRESET", "@preset/general")
THINKING_MAX_TURNS = int(os.getenv("THINKING_MAX_TURNS", "20"))

# =============================================================================
# Media Upload Configuration
# =============================================================================
MEDIA_UPLOAD_DIR = os.getenv("MEDIA_UPLOAD_DIR", "uploads")

# Cache Configuration
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))  # Max conversations in cache

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Channel System Configuration (Phase 5)
CHANNEL_DEBOUNCE_SECONDS = float(os.getenv("CHANNEL_DEBOUNCE_SECONDS", "5"))
CHANNEL_MAX_CHUNK_CHARS = int(os.getenv("CHANNEL_MAX_CHUNK_CHARS", "1500"))
OPENWEBUI_POLL_INTERVAL = float(os.getenv("OPENWEBUI_POLL_INTERVAL", "5.0"))



HEARTBEAT_ENABLED: bool = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"
HEARTBEAT_IDLE_HOURS: float = float(os.getenv("HEARTBEAT_IDLE_HOURS", "6.0"))
HEARTBEAT_COOLDOWN_HOURS: float = float(os.getenv("HEARTBEAT_COOLDOWN_HOURS", "6.0"))
HEARTBEAT_QUIET_HOURS: str = os.getenv("HEARTBEAT_QUIET_HOURS", "23:00-07:00")  # UTC



REFLECTION_CONTEXT_ID: str = os.getenv("REFLECTION_CONTEXT_ID", "__global__")
REFLECTION_ENABLED: bool = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
REFLECTION_PERIODIC_HOURS: float = float(os.getenv("REFLECTION_PERIODIC_HOURS", "6.0"))
REFLECTION_POST_SESSION_MIN_TURNS: int = int(os.getenv("REFLECTION_POST_SESSION_MIN_TURNS", "5"))

# Thresholds for triggering reflection
REFLECTION_THRESHOLD_UNCATEGORIZED: int = int(os.getenv("REFLECTION_THRESHOLD_UNCATEGORIZED", "20"))
REFLECTION_THRESHOLD_GAPS_NO_CRITERIA: int = int(os.getenv("REFLECTION_THRESHOLD_GAPS_NO_CRITERIA", "5"))
REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE: int = int(os.getenv("REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE", "10"))

# Capability Gap Promotion (Phase5 - Part5 of plan.md)
CAPABILITY_GAP_PROMOTION_THRESHOLD: int = int(os.getenv("CAPABILITY_GAP_PROMOTION_THRESHOLD", "3"))



OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/if-prototype-a1",
    "X-Title": "IF Prototype A1"
}


OPENWEBUI_TASK_MARKERS = [
    "### Task:\nSuggest 3-5 relevant follow-up",
    "### Task:\nGenerate a concise, 3-5 word title",
    "### Task:\nGenerate 1-3 broad tags",
]


DIRECTIVE_STORE_ENABLED: bool = os.getenv("DIRECTIVE_STORE_ENABLED", "true").lower() == "true"
DYNAMODB_DIRECTIVES_TABLE = os.getenv("DYNAMODB_DIRECTIVES_TABLE", "if-core")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# =============================================================================
# Model Configuration (all configurable via env vars, defaults use presets)
# =============================================================================

# API model identifier (for external clients connecting to this API)
API_MODEL_NAME = os.getenv("API_MODEL_NAME", "if-prototype")

# Tokenizer model for tiktoken (not LLM calls, just token counting)
TOKENIZER_MODEL = os.getenv("TOKENIZER_MODEL", "gpt-4")

# Model for directive content rewriting
DIRECTIVE_REWRITE_MODEL = os.getenv("DIRECTIVE_REWRITE_MODEL", "openrouter/@preset/heavy")

# Model for conversation condensation (summarizing long conversations)
CONDENSER_MODEL = os.getenv("CONDENSER_MODEL", "anthropic/claude-haiku-4.5")

# Model for condensing user intent into specialist task prompts (cheap/fast)
CONDENSE_INTENT_MODEL = os.getenv("CONDENSE_INTENT_MODEL", "anthropic/claude-haiku-4.5")

# Fallback model for heartbeat pondering (when pondering preset unavailable)
HEARTBEAT_FALLBACK_MODEL = os.getenv("HEARTBEAT_FALLBACK_MODEL", "openrouter/@preset/general")

# Fallback model for presets without defined models
PRESET_FALLBACK_MODEL = os.getenv("PRESET_FALLBACK_MODEL", "openrouter/@preset/general")

# Model for reflection engine and opinion formation
REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "openrouter/@preset/general")

# Reasoning effort passed to the OpenHands LLM for the main agent.
# Valid values: "high", "medium", "low" (silently ignored for models that don't support it).
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "high")

# Reasoning effort for specialist subagents using the SDK agentic loop.
# Defaults to the same value as the main agent.
SPECIALIST_REASONING_EFFORT = os.getenv("SPECIALIST_REASONING_EFFORT", LLM_REASONING_EFFORT)


# =============================================================================
# Terminal Configuration (Static Deployment)
# =============================================================================

WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/app/src/data/conversations")

# Host path for Docker volume access (for workspace file serving)
# Set to empty string to disable workspace file serving
TERMINAL_VOLUME_HOST_ROOT = os.getenv("TERMINAL_VOLUME_HOST_ROOT", "")



# Model for plan execution subagents
ORCHESTRATOR_SUBAGENT_MODEL = os.getenv("ORCHESTRATOR_SUBAGENT_MODEL", "openrouter/@preset/standard")

# Model for parallel analysis subagents (lighter weight for faster analysis)
ORCHESTRATOR_ANALYSIS_MODEL = os.getenv("ORCHESTRATOR_ANALYSIS_MODEL", "openrouter/@preset/air")

# Model for synthesis of parallel analysis results
ORCHESTRATOR_SYNTHESIS_MODEL = os.getenv("ORCHESTRATOR_SYNTHESIS_MODEL", "openrouter/@preset/standard")

# Maximum turns per subagent before timeout
ORCHESTRATOR_MAX_TURNS = int(os.getenv("ORCHESTRATOR_MAX_TURNS", "15"))

# Maximum turns for analysis subagents (usually need fewer)
ORCHESTRATOR_ANALYSIS_MAX_TURNS = int(os.getenv("ORCHESTRATOR_ANALYSIS_MAX_TURNS", "10"))


# =============================================================================
# External Tools Plugin Directory
# =============================================================================

EXTERNAL_TOOLS_PATH = os.getenv("EXTERNAL_TOOLS_PATH", "")
EXTERNAL_TOOLS_FALLBACK = os.getenv(
    "EXTERNAL_TOOLS_FALLBACK",
    str(Path(__file__).parent.parent.parent / "tools")  # project_root/tools/
)

# =============================================================================
# Specialists Directory
# =============================================================================

SPECIALISTS_PATH = os.getenv(
    "SPECIALISTS_PATH",
    str(Path(__file__).parent.parent.parent / "specialists")  # project_root/specialists/
)

# =============================================================================
# Skills Directory (AgentSkills-compliant)
# =============================================================================

SKILLS_PATH = os.getenv(
    "SKILLS_PATH",
    str(Path(__file__).parent.parent.parent / "skills")  # project_root/skills/
)

# =============================================================================
# Health Module Configuration
# =============================================================================

# DynamoDB table name for health program storage
# Note: IF_HEALTH_TABLE_NAME is defined at line 8 in .env.example
IF_HEALTH_TABLE_NAME = os.getenv("IF_HEALTH_TABLE_NAME", "if-health")

# DynamoDB table name for copied session records
IF_SESSIONS_TABLE_NAME = os.getenv("IF_SESSIONS_TABLE_NAME", "if-sessions")

# Partition key value for health program storage
HEALTH_PROGRAM_PK = os.getenv("HEALTH_PROGRAM_PK", "operator")

# =============================================================================
# Infrastructure Tables Configuration
# =============================================================================

# Finance table - versioned financial profile storage
IF_FINANCE_TABLE_NAME = os.getenv("IF_FINANCE_TABLE_NAME", "if-finance")

# Diary entries table - TTL-enabled write-only entries
IF_DIARY_ENTRIES_TABLE_NAME = os.getenv("IF_DIARY_ENTRIES_TABLE_NAME", "if-diary-entries")

# Diary signals table - distilled signals for charting/injection
IF_DIARY_SIGNALS_TABLE_NAME = os.getenv("IF_DIARY_SIGNALS_TABLE_NAME", "if-diary-signals")

# Proposals table - agent-proposed directives/tools
IF_PROPOSALS_TABLE_NAME = os.getenv("IF_PROPOSALS_TABLE_NAME", "if-proposals")

# Default user PK for all infrastructure tables
IF_USER_PK = os.getenv("IF_USER_PK", "operator")

# =============================================================================
# Diary Configuration
# =============================================================================

# TTL for diary entries in days
DIARY_TTL_DAYS = int(os.getenv("DIARY_TTL_DAYS", "3"))

# Interval for automatic signal computation (hours)
DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS = float(os.getenv("DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS", "6.0"))

# Model for diary signal computation
DIARY_SIGNAL_MODEL = os.getenv("DIARY_SIGNAL_MODEL", "openrouter/@preset/air")

# Directory containing health PDF documents for RAG
HEALTH_DOCS_DIR = os.getenv("HEALTH_DOCS_DIR", "docs/health")

# Model for research agent spawned by health tools
RESEARCH_AGENT_MODEL = os.getenv("RESEARCH_AGENT_MODEL", "openrouter/@preset/heavy")


# =============================================================================
# Model Registry Configuration
# =============================================================================

IF_MODELS_TABLE_NAME = os.getenv("IF_MODELS_TABLE_NAME", "if-models")

MODELS_PATH = os.getenv(
    "MODELS_PATH",
    str(Path(__file__).parent.parent.parent / "models")
)

SCRIPTS_PATH = os.getenv(
    "SCRIPTS_PATH",
    str(Path(__file__).parent.parent.parent / "scripts")
)

MODEL_ROUTER_MODEL = os.getenv("MODEL_ROUTER_MODEL", "anthropic/claude-haiku-4.5")
MODEL_ROUTER_ENABLED: bool = os.getenv("MODEL_ROUTER_ENABLED", "true").lower() == "true"

# Model for AI-powered health analytics (correlation analysis, program evaluation)
# Defaults to Claude Sonnet with extended thinking enabled
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "anthropic/claude-sonnet-4.6")
ANALYSIS_MODEL_THINKING_BUDGET = int(os.getenv("ANALYSIS_MODEL_THINKING_BUDGET", "16000"))
ANALYSIS_CACHE_TABLE_NAME = os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache")

# Model settings for user-facing health estimate flows (fatigue, muscle groups,
# accessory e1RM backfill, lift-profile stimulus). These callers hit the raw
# OpenRouter chat API directly, so they use reasoning.effort plus verbosity
# rather than the SDK-only reasoning_effort field.
ESTIMATE_MODEL = os.getenv("ESTIMATE_MODEL", ANALYSIS_MODEL)
ESTIMATE_MODEL_REASONING_EFFORT = os.getenv("ESTIMATE_MODEL_REASONING_EFFORT", "xhigh")
ESTIMATE_MODEL_VERBOSITY = os.getenv("ESTIMATE_MODEL_VERBOSITY", "max")

# Cheaper model for narrow user-facing health helpers such as session note
# drafting, session auto-regulation, and lift-profile rewrite cleanup.
HEALTH_HELPER_MODEL = os.getenv("HEALTH_HELPER_MODEL", "openai/gpt-5.4-mini")
HEALTH_HELPER_MODEL_REASONING_EFFORT = os.getenv("HEALTH_HELPER_MODEL_REASONING_EFFORT", "low")
HEALTH_HELPER_MODEL_VERBOSITY = os.getenv("HEALTH_HELPER_MODEL_VERBOSITY", "low")

# Cheap, low-context model for exercise glossary prose generation.
GLOSSARY_TEXT_MODEL = os.getenv("GLOSSARY_TEXT_MODEL", "google/gemini-3.1-flash-lite")

# Fast model for import classification and resolution
IMPORT_FAST_MODEL = os.getenv("IMPORT_FAST_MODEL", "anthropic/claude-haiku-4.5")

# Interval for refreshing per-provider latency/throughput from OpenRouter (seconds)
MODEL_STATS_REFRESH_INTERVAL = int(os.getenv("MODEL_STATS_REFRESH_INTERVAL", "1800"))  # 30 min

# Interval for full model metadata seed from OpenRouter (seconds)
MODEL_SEED_INTERVAL = int(os.getenv("MODEL_SEED_INTERVAL", "3600"))  # 1 hour

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")
