# Model Selection Rules

These rules guide the planner's `selected_model` value. The planner must still choose only model IDs present in `model_ids.txt`.

## General Policy

- Pick the smallest eligible model that can answer the current turn well.
- Do not default to the cheapest model or the most expensive model.
- Escalate when the request is technical, health-critical, multi-step, stateful, ambiguous, tool-heavy, has repeated failures, includes large files, or depends on long conversation history.
- De-escalate only when the latest turn is clearly short, low-risk, and does not need the deeper context from earlier turns.
- Account for `history.md`, runtime context, and uploaded files. If the prompt is large or the conversation has accumulated a lot of relevant state, choose a robust long-context model rather than a cheap short-context model.

## Simple And Low-Risk Tasks

- Use cheaper, fast models for greetings, short rewrites, quick classification, tiny admin tasks, and simple factual answers that do not require current web data.
- Good defaults: `openai/gpt-5.4-nano`, `openai/gpt-5-nano`, `google/gemini-3.1-flash-lite`, `z-ai/glm-4.7-flash`.
- Use `openai/gpt-5.4-mini`, `z-ai/glm-5-turbo`, or `x-ai/grok-4.1-fast` when the answer still benefits from stronger reasoning but remains low-risk.

## Powerlifting And Health

- Prioritize quality for powerlifting, health, program analysis, training log interpretation, fatigue/readiness reasoning, imports/templates, and explicit training data mutations.
- Default to `z-ai/glm-5.1` for powerlifting coach routes unless the task is purely administrative.
- Use `anthropic/claude-sonnet-4.6` or `openai/gpt-5.4` when the request combines powerlifting with complex technical reasoning, large context, unclear data, or multi-stage analysis.
- Avoid nano/flash-tier models for substantive powerlifting coaching, training mutations, or health-adjacent judgment.

## Coding, Debugging, And Architecture

- For coding, repository edits, debugging, build/test work, software architecture, infrastructure, security review, and migration planning, prioritize correctness over cost.
- Default to `anthropic/claude-sonnet-4.6` for general coding, debugging, and software architecture.
- Use `openai/gpt-5.3-codex` for implementation-heavy repository work, tests, refactors, and build/debug loops.
- Use `openai/gpt-5.4`, `openai/gpt-5.5`, or `anthropic/claude-opus-4.6` for unusually complex, high-risk, or long-context technical work.
- Avoid nano/flash-tier models for code changes unless the task is a very small script or trivial inspection.

## Research And Current Information

- Use web-capable models only when current external information is required.
- Use `perplexity/sonar-pro-search` for broad current research and citation-heavy lookup.
- Use `perplexity/sonar-reasoning` for current research that needs synthesis or careful comparison.
- Use `anthropic/claude-sonnet-4.6:online`, `anthropic/claude-opus-4.6:online`, or `openai/gpt-5.4:online` when the task also needs strong general reasoning.

## Specialist Hints

- `powerlifting_coach`: prefer `z-ai/glm-5.1`; escalate only for very large or cross-domain analysis.
- `coder`, `debugger`, `architect`, `devops`, `secops`, `test_writer`, `refactorer`, `performance_analyst`: prefer `anthropic/claude-sonnet-4.6` or `openai/gpt-5.3-codex`; escalate for high risk or large context.
- `research_assistant` and `financial_analyst` with current-market or current-web requirements: prefer a Perplexity or `:online` model.
- `proofreader`, `email_writer`, `constrained_writer`, `summarizer`, `todo_generator`: use cheaper models unless the source material is long or sensitive.
