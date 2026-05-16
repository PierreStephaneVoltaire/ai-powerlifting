# IF opencode/MCP Migration Plan

This migration replaces the OpenHands orchestrator/specialist/model-router path with a three-stage opencode flow and moves external tools behind Python MCP servers.

## Decisions

- The planning stage always uses `deepseek/deepseek-v4-flash`.
- Selectable execution models come only from `models/model_ids.txt`.
- The model router is removed. The first plan chooses the model for the next stage.
- Specialist prompts remain generated from `specialists/*/specialist.yaml` and `agent.j2`, but the generated opencode agent files must not include router preset/model-pool instructions.
- The generated agents must keep IF's personality, core directives, and the specialist's relevant directives/tool expectations.
- OpenHands SDK imports and the `openhands-sdk` dependency are removed after the opencode/MCP path works.

## Stage 1: Session History And Planning

On every new inbound message, write a session-local history file:

```text
{mount}/{guild_id}/{channel_id}/history.md
```

For non-Discord HTTP/OpenWebUI traffic, use stable fallback identifiers derived from the request cache key so the same session shape is preserved.

Run opencode in plan mode:

```bash
opencode run \
  --agent plan \
  --model deepseek/deepseek-v4-flash \
  --dangerously-skip-permissions \
  --dir {session_dir} \
  "{planner_prompt}"
```

The planner prompt must inject:

- IF personality and core directives.
- Available specialists from `specialists/*/specialist.yaml`.
- Eligible model IDs loaded from `models/model_ids.txt`, grouped by provider/category for readability.
- The current `history.md` location.

The planner must write `{session_dir}/plan.md` with YAML front matter followed by the self-contained next-stage prompt:

```markdown
---
intent_summary: "short summary"
interaction_type: "social|domain|technical"
specialist: "powerlifting_coach"
thinking_mode: false
selected_model: "provider/model-id-from-model_ids.txt"
---

# Prompt

Full self-contained prompt for the next stage.
```

The parser validates all required fields, the interaction type enum, a known specialist slug, and that `selected_model` is present in `models/model_ids.txt`.

## Stage 2: Route

### Social

Call the OpenRouter chat API directly with:

- IF personality.
- Core directives.
- The planner's next-stage prompt.

No MCP tool loop is loaded for social traffic.

### Domain

Call the OpenRouter chat API directly with:

- IF personality.
- Core directives.
- Specialist prompt/directives.
- Relevant MCP tools based on the selected specialist.

The direct LLM loop supports OpenAI-compatible tool calls and dispatches them through the app-side MCP client. This path is the primary route for Powerlifting App tool usage.

### Technical

Run opencode build mode in the session directory:

```bash
opencode run \
  --agent build \
  --model {selected_model} \
  --dangerously-skip-permissions \
  --dir {session_dir} \
  "{technical_prompt}"
```

The build prompt must instruct opencode to write `{session_dir}/response.md`.

Then run an opencode plan-mode review:

```bash
opencode run \
  --agent plan \
  --model deepseek/deepseek-v4-flash \
  --dangerously-skip-permissions \
  --dir {session_dir} \
  "{review_prompt}"
```

The reviewer writes `{session_dir}/review.md`. If line 1 is exactly `RETRY`, rerun build once with the review as additional context. Otherwise deliver the first build result. There is no second retry.

## Stage 3: Deliver

- Technical responses are read from `{session_dir}/response.md`.
- Social/domain responses use the direct LLM response.
- Existing Discord status embeds and slash commands remain intact.
- Existing chunking/delivery behavior remains intact.
- For technical tasks, upload files created in the session directory during build, excluding `history.md`, `plan.md`, `review.md`, and `response.md`.

## Generated opencode Agents

Add a generator script that reads:

- `app/main_system_prompt.txt`
- `specialists/*/specialist.yaml`
- `specialists/*/agent.j2`
- directive metadata from `specialist.directive_types`
- tool/MCP metadata

It writes `.opencode/agent/{specialist}.md` files. The files must describe:

- IF's personality and response posture.
- The specialist's role and constraints.
- Relevant directives and skills.
- Available MCP tool categories.
- Required output behavior.

Generated files must not include `@preset/*`, model-router, tier-router, or OpenHands SDK instructions.

## Tools To MCP

Wrap every plugin in `tools/` as a thin Python MCP server. Tool business logic in `tool.py` stays in place; only the transport changes.

Servers:

- `health`
- `finance`
- `diary`
- `proposals`
- `temporal` for all `tools/temporal_*`
- `supplement_research` for the existing supplement plugin

At app startup, launch all MCP servers as subprocesses and build a tool-name index. `POST /admin/reload-tools` restarts the relevant subprocess and refreshes the index.

For each MCP server:

- Load schemas from `get_schemas()` when present.
- For temporal subprocess-style plugins, load `tool_meta.yaml`.
- Dispatch calls to the existing async `execute(name, args)` functions.
- Return text or JSON-serializable content without altering domain behavior.

Powerlifting App direct calls must use the Python MCP client path instead of direct plugin imports or `ToolRegistry`.

## OpenHands Removal

After the opencode/MCP paths pass the priority tests:

- Remove `openhands-sdk` from `app/requirements.txt`.
- Delete or disconnect `agent/session.py`, OpenHands SDK tool adapters, subagent SDK logic, and dead orchestrator/model-router code.
- Replace `LocalWorkspace` usage with the local session directory manager.
- Keep pure helpers that remain useful: specialists registry, directive store, reflection, memory, routing commands, file metadata parsing, channel delivery, and status embeds.

## Priority Verification

Primary gates:

1. FastAPI powerlifting stats endpoints still call MCP health tools:
   - `GET /api/health/stats/categories`
   - `POST /api/health/stats/analyze`
2. Powerlifting backend routes still work:
   - `/api/stats/categories`
   - `/api/stats/analyze`
   - export routes that invoke IF.
3. Discord inbound message still produces status embeds and a delivered bot message.

Secondary gates:

- Direct domain tool loop can call MCP tools and return results.
- Technical opencode route writes and delivers `response.md`.
- Reviewer `RETRY` reruns build once.
- Technical file uploads exclude only `history.md`, `plan.md`, `review.md`, and `response.md`.
- `rg "openhands|OpenHands|LocalWorkspace"` has no runtime imports after final cleanup.

