# Tarot Reader — Implementation Planning Prompt

Paste this into Claude in planning mode (or as a task for the coder/architect specialist).

---

## Context

You are implementing a `tarot_reader` specialist and a `tarot` tool plugin for the IF agent system.
Read `CLAUDE.md`, `ARCHITECTURE.md`, and `README.md` before writing any code or files.
Follow all existing patterns exactly: specialist auto-discovery via `specialists/*/specialist.yaml`,
tool plugin structure under `tools/<plugin>/`, scoped MCP config via `mcp_servers.yaml`,
and `FILES:` metadata for Discord attachment delivery.

---

## What To Build

### 1. Tool Plugin — `tools/tarot/`

Follow the exact structure of an existing tool plugin (e.g. `tools/diary/` or `tools/temporal_dates/`).
Read an existing `tool.yaml` and `tool.py` before writing these.

#### `tools/tarot/tool.yaml`

```yaml
name: tarot
description: Tarot card draw, meaning lookup, and spread information for the tarot_reader specialist.
tools:
  - name: tarot_draw_cards
    description: >
      Randomly draws N cards from a full 78-card Rider-Waite tarot deck, with optional reversals.
      Returns each drawn card's name, orientation (upright/reversed), position label for the spread,
      and the absolute path to its image asset. The specialist must emit a FILES: line for each
      image path so Discord delivers them as attachments.
    parameters:
      n:
        type: integer
        description: Number of cards to draw. Supported values: 1, 3, 6, 8.
        required: true
      allow_reversed:
        type: boolean
        description: Whether reversed cards are possible. Defaults to true.
        required: false
      spread_type:
        type: string
        description: >
          The spread label to use for position naming. If omitted, default position labels
          are used for the given n. Examples: "past_present_future", "celtic_cross", "one_card".
        required: false

  - name: tarot_card_meaning
    description: >
      Returns the objective, traditional Rider-Waite meaning of a named card in upright or reversed
      orientation. Use this when the operator asks what a card means, asks about tarot rules,
      or wants educational context about a specific card independent of a reading.
    parameters:
      card_name:
        type: string
        description: >
          The card name as spoken naturally. E.g. "three of swords", "the high priestess",
          "ace of wands", "six of cups reversed". The tool normalises casing and orientation.
        required: true
      orientation:
        type: string
        description: "upright or reversed. Defaults to upright if not specified."
        required: false

  - name: tarot_spread_info
    description: >
      Returns the name, position labels, and typical use case for a spread of a given size.
      Use this when recommending a spread to the operator before they draw, so the response
      names the positions they should lay out.
    parameters:
      n:
        type: integer
        description: Spread size. Supported: 1, 3, 6, 8.
        required: true
```

#### `tools/tarot/tool.py`

Implement `async execute(name: str, args: dict) -> dict` with three branches.

**`tarot_draw_cards`:**
- Maintain a hardcoded list of all 78 Rider-Waite card names (22 major arcana + 56 minor arcana).
- Use `random.sample` to draw `n` cards without replacement.
- For each drawn card, randomly assign orientation (upright / reversed) if `allow_reversed` is true.
- Map each card to its image asset path: `tools/tarot/assets/cards/<slug>.png` where `<slug>`
  is the card name lowercased, spaces replaced with underscores, "the_" prefix for major arcana.
  Reversed cards use the same image (the specialist describes the inversion textually).
- Assign spread position labels from the spread definitions below or from `spread_type` if given.
- Return a list of dicts: `{card_name, orientation, position_label, image_path}`.

**`tarot_card_meaning`:**
- Normalise the card name (strip "reversed", detect orientation, lowercase, strip leading "the ").
- Look up from a hardcoded meanings dict (or a JSON file at `tools/tarot/data/meanings.json`).
- Return `{card_name, orientation, keywords: [], upright_meaning: str, reversed_meaning: str, element: str, suit: str|null}`.

**`tarot_spread_info`:**
- Return the spread name and position labels for n = 1, 3, 6, 8 (see spread definitions below).

**Spread definitions:**
```
n=1: "Single Card" — positions: ["The Draw"]
n=3: "Three-Card Spread" — positions: ["Past / Root", "Present / Situation", "Future / Outcome"]
n=6: "Six-Card Spread" — positions: [
       "The Present", "The Challenge", "The Past",
       "The Future", "The Hidden", "The Advice"]
n=8: "Eight-Card Spread" — positions: [
       "The Situation", "The Challenge", "The Root",
       "The Recent Past", "The Best Outcome", "The Near Future",
       "The Self", "The Final Outcome"]
```

#### `tools/tarot/assets/cards/`

Create a placeholder README inside this directory:

```
tools/tarot/assets/cards/README.md
```

Content:
```
# Tarot Card Images

Place 78 PNG card images here, one per card, named as follows:

Major Arcana (22):
  the_fool.png, the_magician.png, the_high_priestess.png, the_empress.png,
  the_emperor.png, the_hierophant.png, the_lovers.png, the_chariot.png,
  strength.png, the_hermit.png, wheel_of_fortune.png, justice.png,
  the_hanged_man.png, death.png, temperance.png, the_devil.png,
  the_tower.png, the_star.png, the_moon.png, the_sun.png,
  judgement.png, the_world.png

Minor Arcana (56): <suit>_<value>.png
  Suits: wands, cups, swords, pentacles
  Values: ace, two, three, four, five, six, seven, eight, nine, ten,
          page, knight, queen, king

Examples:
  ace_of_wands.png, three_of_swords.png, queen_of_cups.png, ten_of_pentacles.png

Reversed cards use the same image file; orientation is handled in text by the specialist.
```

Also implement a fallback in `tool.py`: if the image file does not exist at the expected path,
set `image_path` to `null` and include `"image_missing": true` in the result so the specialist
can tell the operator the image assets are not yet installed rather than crashing.

#### `tools/tarot/data/meanings.json`

Create this file with the full 78-card meanings dataset.
Each entry: `{ "upright_keywords": [], "reversed_keywords": [], "upright": "...", "reversed": "...", "element": "...", "suit": "..." | null }`.
Populate with traditional Rider-Waite meanings. This is a significant data file — be thorough.
Major arcana have `"suit": null`. Minor arcana carry their suit.

---

### 2. MCP Server Registration — `specialists/mcp_servers.yaml`

Add an entry for the tarot tool category following the exact pattern of existing local tool entries:

```yaml
tarot:
  type: local
  command: ["python", "/app/tools/mcp_server.py", "tarot"]
  environment:
    IF_TOOLS_ROOT: /app/tools
    IF_MCP_ALLOWED_TOOLS: "tarot_draw_cards,tarot_card_meaning,tarot_spread_info"
    PYTHONPATH: /app/src:/app
  enabled: true
  timeout: 30000
```

---

### 3. Specialist — `specialists/tarot_reader/`

#### `specialists/tarot_reader/specialist.yaml`

```yaml
slug: tarot_reader
name: Tarot Reader
description: >
  Handles all tarot card reading requests. Routes here when the operator asks for a tarot
  reading, draws cards, asks what a card means, asks about tarot rules or spread types,
  or follows up on a previous reading with new draws. Also routes here when the operator
  mentions specific card names in context of interpretation.
preset: standard
directive_types:
  - personal
  - tone
tools:
  - tarot_draw_cards
  - tarot_card_meaning
  - tarot_spread_info
mcp_servers:
  - tarot
agentic: false
```

#### `specialists/tarot_reader/agent.j2`

Write the full Jinja2 prompt template for this specialist.
The prompt must enforce the following behaviours precisely — these are hard rules, not suggestions:

---

**CORE IDENTITY**

You are a tarot reader. You read the cards. You do not answer the question yourself and then
dress the answer in card language. The cards answer the question. Your job is to interpret
what they say.

---

**RULE 1 — NEVER INVENT DRAWS**

If the operator has not drawn cards and has not asked you to generate them, you do not name
or interpret any cards. You do not hint at what cards might say. You do not pre-answer the question.

---

**RULE 2 — NO CARDS PROVIDED: RECOMMEND A SPREAD**

If the operator asks a question but provides no card draws, call `tarot_spread_info` for
the appropriate spread size and respond with:
- Which spread you are recommending and why
- The exact position labels they should lay out
- An instruction to draw and report back

Spread selection heuristics:
- Binary / gut-check / quick yes-no energy → 1 card
- Situation with clear past-present-future or cause-action-outcome shape → 3 cards
- Complex multi-factor life question → 6 cards
- Major crossroads, significant life decision, full Celtic cross energy → 8 cards

Do not guess or hedge. Pick one spread and commit to it.

---

**RULE 3 — NO PHYSICAL DECK: ASK THEN GENERATE**

If the operator explicitly says they do not have their deck, are at work, or asks you to draw
for them, ask once: "Want me to generate the draw?"

If they confirm, call `tarot_draw_cards` with the appropriate n and `allow_reversed: true`.

For each card returned where `image_path` is not null, emit a FILES: line so Discord
delivers the card image as an attachment:

```
FILES: <image_path>
```

Emit one FILES: line per card, in draw order, before the reading begins.
If `image_missing` is true for a card, note this briefly and continue the reading without the image.

---

**RULE 4 — READING FORMAT**

Always structure a reading in two parts:

**Part 1 — The Cards**
Read each card individually in position order.
- State the card name, orientation, and position label.
- Give the reading for that card in that position. This is the primary interpretation.
  Read the card as it speaks to the question and position. Do not pad or summarise at this stage.

**Part 2 — The Reading**
After all cards are read individually, synthesise. What is the overall narrative?
What tension or alignment exists between the cards? What does the spread say as a whole
about the operator's question? This is where context lands — not before.

Do not swap the order. Do not merge them. Part 1 first, Part 2 second.

---

**RULE 5 — FOLLOW-UP HANDLING**

In a continuing conversation about a reading, check whether the follow-up question:
a) Can be answered from the existing draw — if so, interpret from what was already pulled.
b) Is a new question that warrants a new draw — if so, say so and recommend a spread size.
c) Is a meta question about tarot (card meanings, rules, spread logic) — answer it directly
   using `tarot_card_meaning` or `tarot_spread_info` as needed. No draw required.

Do not automatically pull new cards for every follow-up. Only recommend new draws when the
question genuinely cannot be answered by the cards already on the table.

---

**RULE 6 — EDUCATIONAL MODE**

If the operator asks what a card means outside of a reading, asks about tarot rules, asks
how a spread works, or asks about the suits, arcana, elements, or any structural aspect of
tarot — answer it directly and thoroughly. Call `tarot_card_meaning` for individual card
lookups. This is informational, not a reading. You do not need a question or a draw for this.

---

**TONE**

Read seriously. Do not over-mystify or perform mysticism. Do not editorialize toward a
conclusion before the cards are read. Do not use the reading to push advice you already had.
The cards have something to say. Let them say it.

If a card is uncomfortable or its meaning is hard, read it straight.
Softening is not your job. Context is.

---

**TOOL PROTOCOL**

{{ tool_protocol }}

**Allowed tools:** `tarot_draw_cards`, `tarot_card_meaning`, `tarot_spread_info`

---

**RUNTIME CONTEXT**

{{ runtime_context }}

---

**CONVERSATION HISTORY**

{{ history }}

---

**OPERATOR MESSAGE**

{{ message }}

---

### 4. Planner Routing Signals

The specialist description in `specialist.yaml` is what the planner reads. Make sure it is
specific enough to route correctly. Tarot-adjacent signals that should route here:
- Card names mentioned by the operator (Three of Swords, The Fool, etc.)
- Words: tarot, reading, spread, draw, pull, deck, cards, arcana, reversed
- Follow-up messages in a session that already routed to `tarot_reader`

The planner should NOT route here for: general divination questions with no tarot framing,
astrology, numerology, or other non-tarot practices (those are social or would need their
own specialist).

---

### 5. Verification Checklist

After implementation, verify:

- [ ] `specialist.yaml` is valid YAML and discoverable by `agents/specialists.py` auto-scan
- [ ] `mcp_servers.yaml` entry is consistent with other local tool entries
- [ ] `tool.py` `execute()` handles all three tool names and returns clean dicts
- [ ] All 78 card slugs are accounted for in the draw pool
- [ ] `meanings.json` has an entry for all 78 cards
- [ ] Reversed orientation is handled in `tarot_card_meaning` (strip "reversed" from name, set orientation)
- [ ] `FILES:` lines are emitted correctly for image paths (test with a mock draw)
- [ ] `image_missing: true` fallback does not crash the specialist
- [ ] The specialist prompt compiles through the Jinja2 renderer without errors
- [ ] A test message "should I go to the gym today or skip" with no cards routes to `tarot_reader`,
      returns a spread recommendation, and does NOT name any cards or pre-answer the question
- [ ] A test message "three of swords, two of swords, ace of swords" (cards provided) triggers
      a proper two-part reading with no fabricated context
- [ ] A test message "what does the high priestess mean" routes to `tarot_reader`, calls
      `tarot_card_meaning`, and returns objective meaning without requiring a question or draw

---

### 6. Do Not

- Do not add tarot tools to any other specialist's allowed tool list
- Do not add tarot MCP server to any other specialist's `mcp_servers`
- Do not create a portal or DynamoDB table for tarot — this is stateless
- Do not store reading history in LanceDB user facts unless the operator explicitly asks
  the system to remember something from a reading
- Do not modify `flow/runner.py`, `flow/plan.py`, or `api/completions.py` — the existing
  routing infrastructure handles this specialist without changes
