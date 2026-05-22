# This module is intentionally empty.
# Health stats tools (powerlifting_filter_categories, analyze_powerlifting_stats,
# powerlifting_ranking_percentile) are exposed as MCP tools via tools/health/tool.py
# and called through POST /v1/chat/completions with X-Direct-Tool-Invoke: true.
# The backend stats router uses invokeToolDirect() — no custom FastAPI routes needed here.
