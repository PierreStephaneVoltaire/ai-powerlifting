---
name: deep_think
description: Extended reasoning for one hard question, with optional specialist handoffs for evidence or domain checks.
---

# Deep Think

## When To Use

Use this when the operator explicitly asks IF to think deeply, reason before answering, pressure-test a conclusion, find a root cause, or analyze one difficult question.

Do not use it for routine social replies, simple single-domain lookups, or implementation work that should go directly to a technical/domain specialist.

## Protocol

1. Restate the core question in one sentence.
2. Identify assumptions, unknowns, and the domain evidence needed.
3. If one domain specialist must inspect data or tools, emit one `HANDOFF_REQUIRED` block to that specialist.
4. If the reasoning can be completed locally, write concise notes under `plans/deep-think.md`.
5. Produce the final answer in IF's voice, preserving caveats and risks.

## Handoff Format

```text
HANDOFF_REQUIRED:
  target: dialectic
  task: "Pressure-test the central claim and return strongest objections plus synthesis."
  context: "Question, assumptions, and relevant evidence."
```

Use `dialectic` for adversarial reasoning, `decision_analyst` for weighted tradeoffs, and a domain specialist when tools or domain data are required.
