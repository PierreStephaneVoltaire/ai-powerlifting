---
name: parallel_analysis
description: Multi-perspective analysis of one artifact or decision, using specialist handoffs for independent lenses.
---

# Parallel Analysis

## When To Use

Use this when the operator explicitly asks for multiple angles, adversarial review, security/performance/architecture review, or independent perspectives on the same artifact.

## Protocol

1. Identify two or three independent lenses. Do not exceed three unless the operator asked for more.
2. Emit one `HANDOFF_REQUIRED` block per lens, ordered by importance.
3. Ask each handoff specialist to write findings to a named file under `findings/` when the output is long.
4. Synthesize returned findings into: agreement, disagreement, risk ranking, and recommended action.
5. Preserve severe findings exactly; do not smooth them into vague advice.

## Common Lenses

- Security: `secops`
- Performance: `performance_analyst`
- Architecture: `architect`
- Code correctness: `code_reviewer`
- Product/user impact: `product_owner` or `product_manager`
- Training/nutrition: `powerlifting_coach`

## Handoff Format

```text
HANDOFF_REQUIRED:
  target: secops
  task: "Review the attached plan for concrete security risks and missing controls."
  context: "Same artifact and constraints as the original operator request."
```
