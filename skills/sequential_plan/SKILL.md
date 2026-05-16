---
name: sequential_plan
description: Dependency-aware planning for multi-step goals where each step changes the state for the next step.
---

# Sequential Plan

## When To Use

Use this when the operator asks to plan a migration, rollout, investigation, debugging path, or any goal where step N depends on step N-1.

## Protocol

1. Create or update a plan file under `plans/` using markdown checkboxes:
   - `[ ]` open
   - `[x]` done
   - `[!]` needs adjustment
   - `[?]` blocked
2. Separate critical-path steps from parallel side work.
3. For each step that requires a different specialist, emit a `HANDOFF_REQUIRED` block in dependency order.
4. After a handoff result returns, update the plan file before continuing.
5. The final response should summarize current state, completed steps, blocked items, and the next executable action.

## Handoff Format

```text
HANDOFF_REQUIRED:
  target: coder
  task: "Implement step 2 from plans/auth-migration.md exactly as scoped."
  context: "Include relevant decisions, files, constraints, and prior step output."
```

Do not pretend a downstream specialist ran. Only state completed work that was actually done in the workspace or returned by a handoff.
