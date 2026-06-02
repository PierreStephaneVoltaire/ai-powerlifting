



import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is required")

LLM_API_KEY = os.getenv("LLM_API_KEY", OPENROUTER_API_KEY)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

MESSAGE_WINDOW = int(os.getenv("MESSAGE_WINDOW", "8"))
CRISIS_THRESHOLD = float(os.getenv("CRISIS_THRESHOLD", "0.3"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
CONFIDENCE_GAP = float(os.getenv("CONFIDENCE_GAP", "0.2"))
RECLASSIFY_MESSAGE_COUNT = int(os.getenv("RECLASSIFY_MESSAGE_COUNT", "4"))

SUGGESTION_MODEL = os.getenv("SUGGESTION_MODEL", "mistralai/mistral-nemo")

SCORING_MODELS_STR = os.getenv(
    "SCORING_MODELS",
    "google/gemini-2.5-flash-lite,qwen/qwen3-32b,z-ai/glm-4.7-flash"
)
SCORING_MODELS: List[str] = [
    model.strip() for model in SCORING_MODELS_STR.split(",") if model.strip()
]

GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "")

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")

def get_project_root() -> Path:

    current = Path(__file__).resolve().parent.parent
    if (current.parent / "tools").exists():
        return current.parent
    return current

PROJECT_ROOT = get_project_root()

def get_app_src(root: Path) -> Path:

    if (root / "app" / "src").exists():
        return root / "app" / "src"
    return root / "src"

APP_SRC = get_app_src(PROJECT_ROOT)

SANDBOX_PATH = os.getenv("SANDBOX_PATH", "./sandbox")
MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "./data/memory_db")
PERSISTENCE_DIR = os.getenv("PERSISTENCE_DIR", "./data/conversations")

FACTS_BASE_PATH = os.getenv("FACTS_BASE_PATH", "./data/facts")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

STORAGE_DB_PATH = os.getenv("STORAGE_DB_PATH", "./data/store.db")
STORE_BACKEND = os.getenv("STORE_BACKEND", "sqlite")

TOPIC_SHIFT_MODEL = os.getenv("TOPIC_SHIFT_MODEL", "z-ai/glm-4.7-flash")

CONTEXT_CONDENSE_THRESHOLD = int(os.getenv("CONTEXT_CONDENSE_THRESHOLD", "250000"))

TOOL_OUTPUT_CHAR_LIMIT = int(os.getenv("TOOL_OUTPUT_CHAR_LIMIT", "200000"))

TIER_UPGRADE_THRESHOLD = float(os.getenv("TIER_UPGRADE_THRESHOLD", "0.65"))

TIER_AIR_LIMIT = int(os.getenv("TIER_AIR_LIMIT", "100000"))
TIER_STANDARD_LIMIT = int(os.getenv("TIER_STANDARD_LIMIT", "200000"))
TIER_HEAVY_LIMIT = int(os.getenv("TIER_HEAVY_LIMIT", "1000000"))

TIER_AIR_PRESET = os.getenv("TIER_AIR_PRESET", "@preset/air")
TIER_STANDARD_PRESET = os.getenv("TIER_STANDARD_PRESET", "@preset/standard")
TIER_HEAVY_PRESET = os.getenv("TIER_HEAVY_PRESET", "@preset/heavy")

OPENCODE_BIN = os.getenv("OPENCODE_BIN", "")
OPENCODE_PLANNER_MODEL = os.getenv("OPENCODE_PLANNER_MODEL", "deepseek/deepseek-v4-flash")
OPENCODE_TIMEOUT_SECONDS = int(os.getenv("OPENCODE_TIMEOUT_SECONDS", "900"))
OPENCODE_WORKSPACE_BASE = os.getenv(
    "OPENCODE_WORKSPACE_BASE",
    os.getenv("WORKSPACE_BASE", "/app/src/data/conversations"),
)
IF_DIRECT_LLM_TOOL_ROUNDS = int(os.getenv("IF_DIRECT_LLM_TOOL_ROUNDS", "8"))
IF_DEFAULT_DIRECT_MODEL = os.getenv("IF_DEFAULT_DIRECT_MODEL", "openai/gpt-5.4-mini")
IF_TECHNICAL_ARTIFACT_EXCLUDES = {
    "history.md",
    "history.json",
    "opencode.json",
    "plan.md",
    "review.md",
    "response.md",
    "status.log",
}

MCP_SERVER_CATEGORIES = [
    item.strip()
    for item in os.getenv(
        "MCP_SERVER_CATEGORIES",
        "health,finance,diary,proposals,supplement_research,"
        "temporal_age,temporal_city_time,temporal_duration,temporal_from_unix,"
        "temporal_resolve,temporal_timezone,temporal_to_unix,tarot",
    ).split(",")
    if item.strip()
]

SPECIALIST_PRESET = os.getenv("SPECIALIST_PRESET", "general")

SPECIALIST_MAX_TURNS = int(os.getenv("SPECIALIST_MAX_TURNS", "15"))

AGENTIC_MAX_ITERATIONS = int(os.getenv("AGENTIC_MAX_ITERATIONS", "25"))

THINKING_PRESET = os.getenv("THINKING_PRESET", "@preset/general")
THINKING_MAX_TURNS = int(os.getenv("THINKING_MAX_TURNS", "20"))

MEDIA_UPLOAD_DIR = os.getenv("MEDIA_UPLOAD_DIR", "uploads")

CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

CHANNEL_DEBOUNCE_SECONDS = float(os.getenv("CHANNEL_DEBOUNCE_SECONDS", "5"))
CHANNEL_MAX_CHUNK_CHARS = int(os.getenv("CHANNEL_MAX_CHUNK_CHARS", "1500"))
OPENWEBUI_POLL_INTERVAL = float(os.getenv("OPENWEBUI_POLL_INTERVAL", "5.0"))

IF_EXECUTION_REGISTRY_TABLE_NAME = os.getenv("IF_EXECUTION_REGISTRY_TABLE_NAME", "if-agent-execution-registry")
CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS = int(os.getenv("CHANNEL_CLASSIFIER_MAX_WAIT_SECONDS", "300"))
CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS = float(
    os.getenv("CHANNEL_CLASSIFIER_DEBOUNCE_SECONDS", os.getenv("CHANNEL_DEBOUNCE_SECONDS", "45"))
)
OUTBOUND_LOCK_DURATION_SECONDS = int(os.getenv("OUTBOUND_LOCK_DURATION_SECONDS", "120"))
OUTBOUND_DRAIN_BATCH_SIZE = int(os.getenv("OUTBOUND_DRAIN_BATCH_SIZE", "10"))
OUTBOUND_SEND_TIMEOUT_SECONDS = int(os.getenv("OUTBOUND_SEND_TIMEOUT_SECONDS", "30"))
OPENCODE_CANCEL_GRACE_SECONDS = int(os.getenv("OPENCODE_CANCEL_GRACE_SECONDS", "5"))
OPENCODE_CANCEL_POLL_INTERVAL_SECONDS = float(os.getenv("OPENCODE_CANCEL_POLL_INTERVAL_SECONDS", "3.0"))

HEARTBEAT_ENABLED: bool = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"
HEARTBEAT_IDLE_HOURS: float = float(os.getenv("HEARTBEAT_IDLE_HOURS", "6.0"))
HEARTBEAT_COOLDOWN_HOURS: float = float(os.getenv("HEARTBEAT_COOLDOWN_HOURS", "6.0"))
HEARTBEAT_QUIET_HOURS: str = os.getenv("HEARTBEAT_QUIET_HOURS", "23:00-07:00")

REFLECTION_CONTEXT_ID: str = os.getenv("REFLECTION_CONTEXT_ID", "__global__")
REFLECTION_ENABLED: bool = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
REFLECTION_PERIODIC_HOURS: float = float(os.getenv("REFLECTION_PERIODIC_HOURS", "6.0"))
REFLECTION_POST_SESSION_MIN_TURNS: int = int(os.getenv("REFLECTION_POST_SESSION_MIN_TURNS", "5"))

REFLECTION_THRESHOLD_UNCATEGORIZED: int = int(os.getenv("REFLECTION_THRESHOLD_UNCATEGORIZED", "20"))
REFLECTION_THRESHOLD_GAPS_NO_CRITERIA: int = int(os.getenv("REFLECTION_THRESHOLD_GAPS_NO_CRITERIA", "5"))
REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE: int = int(os.getenv("REFLECTION_THRESHOLD_OPINIONS_NO_RESPONSE", "10"))

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

API_MODEL_NAME = os.getenv("API_MODEL_NAME", "if-prototype")

TOKENIZER_MODEL = os.getenv("TOKENIZER_MODEL", "gpt-4")

DIRECTIVE_REWRITE_MODEL = os.getenv("DIRECTIVE_REWRITE_MODEL", "openrouter/@preset/heavy")

CONDENSER_MODEL = os.getenv("CONDENSER_MODEL", "anthropic/claude-haiku-4.5")

CONDENSE_INTENT_MODEL = os.getenv("CONDENSE_INTENT_MODEL", "anthropic/claude-haiku-4.5")

HEARTBEAT_FALLBACK_MODEL = os.getenv("HEARTBEAT_FALLBACK_MODEL", "openrouter/@preset/general")

PRESET_FALLBACK_MODEL = os.getenv("PRESET_FALLBACK_MODEL", "openrouter/@preset/general")

REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "openrouter/@preset/general")

LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "high")

SPECIALIST_REASONING_EFFORT = os.getenv("SPECIALIST_REASONING_EFFORT", LLM_REASONING_EFFORT)

WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/app/src/data/conversations")

TERMINAL_VOLUME_HOST_ROOT = os.getenv("TERMINAL_VOLUME_HOST_ROOT", "")

ORCHESTRATOR_SUBAGENT_MODEL = os.getenv("ORCHESTRATOR_SUBAGENT_MODEL", "openrouter/@preset/standard")

ORCHESTRATOR_ANALYSIS_MODEL = os.getenv("ORCHESTRATOR_ANALYSIS_MODEL", "openrouter/@preset/air")

ORCHESTRATOR_SYNTHESIS_MODEL = os.getenv("ORCHESTRATOR_SYNTHESIS_MODEL", "openrouter/@preset/standard")

ORCHESTRATOR_MAX_TURNS = int(os.getenv("ORCHESTRATOR_MAX_TURNS", "15"))

ORCHESTRATOR_ANALYSIS_MAX_TURNS = int(os.getenv("ORCHESTRATOR_ANALYSIS_MAX_TURNS", "10"))

EXTERNAL_TOOLS_PATH = os.getenv("EXTERNAL_TOOLS_PATH", "")
EXTERNAL_TOOLS_FALLBACK = os.getenv(
    "EXTERNAL_TOOLS_FALLBACK",
    str(PROJECT_ROOT / "tools")
)

SPECIALISTS_PATH = os.getenv(
    "SPECIALISTS_PATH",
    str(PROJECT_ROOT / "specialists")
)

SKILLS_PATH = os.getenv(
    "SKILLS_PATH",
    str(PROJECT_ROOT / "skills")
)

IF_HEALTH_TABLE_NAME = os.getenv("IF_HEALTH_TABLE_NAME", "if-health")

IF_TEMPLATES_TABLE_NAME = os.getenv("IF_TEMPLATES_TABLE_NAME", "if-health-templates")
IF_TEMPLATES_LIBRARY_PK = os.getenv("IF_TEMPLATES_LIBRARY_PK", "template_library")

IF_SESSIONS_TABLE_NAME = os.getenv("IF_SESSIONS_TABLE_NAME", "if-sessions")

HEALTH_PROGRAM_PK = os.getenv("HEALTH_PROGRAM_PK", "operator")

IF_FINANCE_TABLE_NAME = os.getenv("IF_FINANCE_TABLE_NAME", "if-finance")

IF_DIARY_ENTRIES_TABLE_NAME = os.getenv("IF_DIARY_ENTRIES_TABLE_NAME", "if-diary-entries")

IF_DIARY_SIGNALS_TABLE_NAME = os.getenv("IF_DIARY_SIGNALS_TABLE_NAME", "if-diary-signals")

IF_PROPOSALS_TABLE_NAME = os.getenv("IF_PROPOSALS_TABLE_NAME", "if-proposals")

IF_USER_PK = os.getenv("IF_USER_PK", "operator")

DIARY_TTL_DAYS = int(os.getenv("DIARY_TTL_DAYS", "3"))

DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS = float(os.getenv("DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS", "6.0"))

DIARY_SIGNAL_MODEL = os.getenv("DIARY_SIGNAL_MODEL", "openrouter/@preset/air")

HEALTH_DOCS_DIR = os.getenv("HEALTH_DOCS_DIR", "docs/health")

RESEARCH_AGENT_MODEL = os.getenv("RESEARCH_AGENT_MODEL", "openrouter/@preset/heavy")

IF_MODELS_TABLE_NAME = os.getenv("IF_MODELS_TABLE_NAME", "if-models")

MODELS_PATH = os.getenv(
    "MODELS_PATH",
    str(PROJECT_ROOT / "models")
)

SCRIPTS_PATH = os.getenv(
    "SCRIPTS_PATH",
    str(PROJECT_ROOT / "scripts")
)

ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "anthropic/claude-sonnet-4.6")
ANALYSIS_MODEL_THINKING_BUDGET = int(os.getenv("ANALYSIS_MODEL_THINKING_BUDGET", "16000"))
ANALYSIS_CACHE_TABLE_NAME = os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache")

ESTIMATE_MODEL = os.getenv("ESTIMATE_MODEL", ANALYSIS_MODEL)
ESTIMATE_MODEL_REASONING_EFFORT = os.getenv("ESTIMATE_MODEL_REASONING_EFFORT", "xhigh")
ESTIMATE_MODEL_VERBOSITY = os.getenv("ESTIMATE_MODEL_VERBOSITY", "max")

HEALTH_HELPER_MODEL = os.getenv("HEALTH_HELPER_MODEL", "openai/gpt-5.4-mini")
HEALTH_HELPER_MODEL_REASONING_EFFORT = os.getenv("HEALTH_HELPER_MODEL_REASONING_EFFORT", "low")
HEALTH_HELPER_MODEL_VERBOSITY = os.getenv("HEALTH_HELPER_MODEL_VERBOSITY", "low")

GLOSSARY_TEXT_MODEL = os.getenv("GLOSSARY_TEXT_MODEL", "google/gemini-3.1-flash-lite")

IMPORT_FAST_MODEL = os.getenv("IMPORT_FAST_MODEL", "anthropic/claude-haiku-4.5")

MODEL_STATS_REFRESH_INTERVAL = int(os.getenv("MODEL_STATS_REFRESH_INTERVAL", "1800"))

MODEL_SEED_INTERVAL = int(os.getenv("MODEL_SEED_INTERVAL", "3600"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")
