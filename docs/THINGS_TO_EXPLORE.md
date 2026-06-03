# Roadmap & Future Work

Known gaps, planned features, and AI concepts to add — ordered by impact on learning goals and system maturity.

---

## High Priority — Evaluation & Measurement

These fill the biggest gap in the project: showing that things work quantitatively, not just "it feels right."

### Retrieval Evaluation

Two RAG pipelines (LanceDB user facts, ChromaDB health docs) with no retrieval quality measurement.

**Plan**: Build a simple eval harness with 50-100 test queries from real usage. Measure precision@k, recall@k, MRR. Use this to:

- Compare embedding models (current: all-MiniLM-L6-v2 — is it the right choice?)
- Validate chunking strategy (500 tokens, 50 overlap)
- Identify retrieval failure modes

**Concepts covered**: Information retrieval metrics, embedding model comparison, quantitative evaluation.

## High Priority — Security & Safety

### Authentication and Access Control

**Current state**: None. Any user in a registered Discord channel can trigger agent execution.

**Needed**:

- Per-user allowlist
- Per-channel permissions
- Request-level identity propagation (who said what)

### Prompt Injection Defense

Multi-user channels are a textbook prompt injection surface — User A's input becomes context for User B's request.

**Needed**:

- Input sanitization layer
- System/user message boundary enforcement
- Injection attempt detection and logging
- Per-user fact isolation within shared channels

### Hooks and Guardrails

No pre-/post-execution hooks. No content policy enforcement beyond LLM-level refusals.

**Needed for safe multi-user deployment**:

- Pre-execution validation (input guard)
- Post-execution output checks
- Tool use boundaries (what stops the agent from destructive commands?)

---

## Medium Priority — Architecture Improvements

### Multi-Provider Support

LiteLLM as a proxy covers Bedrock, direct Anthropic/OpenAI/Google APIs, and local models (Ollama) without app code changes — point `LLM_BASE_URL` at a LiteLLM instance.

**Planned**: AWS Bedrock.

### Platform Expansion

Slack and Teams planned. Study Hermes's unified messaging gateway design first — a single externally-loadable adapter interface is cleaner than per-platform hardcoded imports.

### FTS5 + Vector Hybrid Memory

LanceDB (vector) excels at semantic similarity. FTS5 (full-text) excels at exact keyword recall. They're complementary. A hybrid query layer would cover both — "find facts about my squat PR" (keyword) and "what are my fitness goals" (semantic) from the same store.

**Concepts covered**: Hybrid retrieval, keyword vs semantic search tradeoffs.

## Lower Priority — Capability Expansion

### Self-Extending Tools

IF's plugin architecture is structurally ready (YAML + Python + hot reload). The gap is the generation step: an agent that writes a new plugin and triggers `POST /admin/reload-tools`.

**Concepts covered**: Meta-programming, runtime system extension.

### Modalities

Currently: text in, text out, vision input via `read_media`.

Missing: TTS, image generation, audio input.

### Knowledge Graph Augmentation

User facts have implicit relationships (project X uses technology Y, person Z works at company W). A lightweight knowledge graph layer alongside vector search could improve relationship-heavy retrieval.

**Concepts covered**: Knowledge representation, graph-based reasoning, hybrid retrieval.

### Prompt-Level Distillation

Capture outputs from expensive models (Opus, GPT-5.4) and use them as few-shot examples for cheaper models on similar future tasks. No fine-tuning needed — prompt-level knowledge transfer.

**Concepts covered**: Knowledge distillation, few-shot learning, cost optimization.

### AgentSkills Marketplace

IF's skills are already SKILL.md compliant. Publishing to agentskills.io enables sharing skills with 30+ compliant agents (GitHub Copilot, Claude Code, Cursor, Goose, Spring AI, etc.).
