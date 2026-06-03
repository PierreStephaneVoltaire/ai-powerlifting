═══ IF RUNTIME COMPATIBILITY ═══
- The IF prompt and DynamoDB directives may mention orchestration tool names. Treat those names as runtime protocols unless this prompt exposes a shell command for them.
- `list_specialists`, `condense_intent`, and the first `spawn_specialist` step are handled by IF before this run: `plan.md` selected the specialist and this prompt contains the condensed task.
- If another specialist is required, end your response with `HANDOFF_REQUIRED:` blocks. IF will execute them in order with the target specialist.
- `deep_think`, `execute_plan`, and `analyze_parallel` are now thinking-mode skills. Use mounted markdown files under `plans/` for shared state and HANDOFF_REQUIRED blocks for specialist work.
- `plan_append`, `plan_read`, `plan_list`, and `plan_grep` map to normal filesystem operations under `plans/`.
- `memory_search` maps to `user_facts_search`; `memory_add` maps to `user_facts_add`; both are exposed through the runtime CLI below.
- `read_media` maps to selecting `media_reader` or using files attached to this opencode run with `--file`; do not invent visual details if the attachment is unavailable.
- Tool-failure directives apply to MCP/runtime CLI failures. Report the exact command/tool name and error.
- Write specialists such as `health_write` and `finance_write` remain handoff-only unless the operator explicitly asked for a mutation and the planner selected that write specialist directly.

