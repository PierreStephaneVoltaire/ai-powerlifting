# NoLift — Budget Page Overhaul
## Product Specification & Parallel Story Map

**Author:** PM  
**Status:** Ready for implementation  
**Spawning model:** Each BUD-XX story is self-contained and safe to implement in parallel. Read the **Shared Contract** section first — it defines the data shapes all stories must agree on. The data model story (BUD-01) has no UI work and can run concurrently with BUD-02 through BUD-05.

---

## Context & Problem Statement

The Budget page exists today but is fundamentally broken as a user experience:

- Six large "Add X" buttons are the primary entry point — they collapse into a mess on mobile.
- Items render as oversized cards (photo placeholder + every field visible at once) — unusable on an iPhone SE (~375 px wide).
- The "Federation memberships" tab is a category, not a tab — it belongs inside the items table.
- Forms ask for information that doesn't always apply (photo for a gym membership? exact date for a recurring subscription?).
- There is no concept of monthly budget cap, no way to see if you're over or under.
- There is no structured priority system — athletes and coaches cannot tell at a glance what is essential vs optional.
- There is no AI surface on this page despite it being the exact kind of triage problem AI is good at.

**The goal:** A tight, mobile-first budget tool that athletes and coaches can use together to track meet-prep spending, assign priorities, and make trade-off decisions with AI help when they're approaching their monthly cap.

**Guiding principle:** Comp day is the absolute north star. Anything that is required for the athlete to walk onto the platform (entry fee, transport, weigh-in food if cutting) is `MANDATORY` and can never be cut by the AI advisor. Everything else is ranked below that.

---

## Who uses this page

| User | Auth State | What they do |
|---|---|---|
| Athlete (self) | Authenticated | Full read/write. Sets monthly budget, enters and edits expenses, runs AI analysis. |
| Coach | Authenticated, viewing athlete profile | Read-only. Can see all items, totals, priorities. Cannot add or edit. May add annotation comments (see BUD-05). |
| Unauthenticated visitor | Not authenticated | Blocked — existing `readOnly` flag already gates writes; this page should show a login prompt instead of dummy data. |

---

## Page Structure (new)

The page has **four tabs**, not six buttons:

```
Budget
├── Overview          ← monthly cap, totals, trend sparklines
├── Items             ← the table (replaces cards + 6-button add flow)
├── Timeline          ← visual month-by-month spend chart anchored to comp dates
└── AI Advisor        ← AI triage panel
```

A persistent **budget status bar** lives above the tabs at all times (except when unauthenticated):

```
[ CAD $450 / month ]   Spent this month: $312   Remaining: $138   [ Edit cap ]
```

If the athlete is over budget, the bar flips to a warning state:

```
[ ⚠ OVER BUDGET by $47 ]   Monthly cap: $450   Spent: $497
```

---

## Shared Contract (all stories must agree on this)

### Expense Item Shape

```
BudgetItem {
  id:             string        // UUID
  user_pk:        string        // partition key (existing mapped_pk pattern)
  
  // Core identity
  name:           string        // "Fortis Fitness", "Creatine", "CPU meet entry"
  category:       CategoryEnum  // see category list below
  priority_tier:  PriorityEnum  // MANDATORY | IMPORTANT | OPTIONAL
  
  // Cost
  cost:           number        // always stored in user's home currency
  currency:       string        // "CAD", "USD" — copied from user settings at write time
  
  // Recurrence
  recurrence:     RecurrenceEnum  // ONE_TIME | MONTHLY | QUARTERLY | ANNUAL
  
  // Date — flexible precision
  date_precision: "exact" | "month"
  start_date:     string        // YYYY-MM-DD if exact; YYYY-MM if month
  end_date:       string | null // null = ongoing for recurring; irrelevant for one-time
  
  // Comp linkage
  comp_linked:    boolean       // true = tied to a specific competition
  competition_id: string | null // FK to if-powerlifting-user-competitions
  
  // Purchase status
  purchased:      boolean
  purchased_date: string | null // YYYY-MM-DD, set when purchased = true
  
  // Optional extras
  notes:          string | null
  photo_s3_key:   string | null // keep existing S3 support, just stop surfacing it prominently
  
  // Meta
  created_at:     string        // ISO8601
  updated_at:     string        // ISO8601
}
```

### CategoryEnum values

```
equipment          // belt, shoes, singlet, knee sleeves, wrist wraps, chalk
supplement         // creatine, protein, pre-workout, vitamins, ashwagandha
gym_membership     // recurring gym cost
federation_membership // annual federation dues (CPU, IPF, USAPL, etc.)
coaching           // coach fee (recurring or per-block)
app_subscription   // NoLift or other training apps
competition_entry  // meet entry fee
transport          // flights, gas, Uber to venue
accommodation      // hotel, Airbnb
food_comp_day      // food on competition day
food_weigh_in      // post weigh-in refeeding
food_prep          // regular nutrition during prep (meal prep, groceries bump)
recovery           // physio, massage, sauna
other              // catch-all
```

### PriorityEnum values

```
MANDATORY   // comp fails or performance tanks without this
IMPORTANT   // meaningfully affects outcome — budget for this before optional
OPTIONAL    // nice to have; first to cut if over budget
```

### BudgetConfig Shape

```
BudgetConfig {
  user_pk:         string
  monthly_cap:     number        // athlete's monthly budget target
  currency:        string
  notes:           string | null // free text ("Trying to keep total prep under $2k")
  updated_at:      string
}
```

### RecurrenceEnum values

```
ONE_TIME    // bought once
MONTHLY     // hits every month (gym membership, coaching, supplements)
QUARTERLY   // hits every 3 months
ANNUAL      // hits once a year (federation dues)
```

---

## Story Map

---

### BUD-01 · Data Model, API Endpoints & Schema Migration
**Type:** Backend + Infrastructure  
**Parallel safety:** No UI; runs independently of all other stories. Other stories mock API responses until this lands.

#### User Stories
- As a backend, I need a `BudgetConfig` record per user so the system knows their monthly cap and currency.
- As a backend, I need `BudgetItem` records that support flexible date precision, competition linkage, and priority tiers.

#### Background
The existing `if-powerlifting-budget` DynamoDB table already exists (Terraform at `terraform/budget.tf`). The current schema does not support priority tiers, date precision toggles, or budget cap config. We need to evolve the schema without breaking existing items — a migration or a graceful default-fill strategy is acceptable.

#### Acceptance Criteria

**Data model:**
- [ ] `BudgetConfig` is stored as a single item per user in the budget table (or a new `if-powerlifting-budget-config` table — implementer's call based on access patterns).
- [ ] `BudgetItem` supports all fields in the Shared Contract above. Any existing item missing `priority_tier` defaults to `OPTIONAL`. Any item missing `date_precision` defaults to `"exact"` if `purchased_date` exists, else `"month"`.
- [ ] `category` enum is expanded to include all values in the Shared Contract. Existing `"Gym membership"` values (note the current mixed casing) are migrated/normalised to `gym_membership`.

**API endpoints:**

Budget Config:
```
GET  /api/budget/config              → { monthly_cap, currency, notes }
PUT  /api/budget/config              → upsert config
```

Budget Items (all respect the existing `mapped_pk` / `readOnly` middleware):
```
GET    /api/budget/items             → BudgetItem[]  (optionally ?comp_id=, ?category=, ?priority=)
POST   /api/budget/items             → create item, returns created item
PUT    /api/budget/items/:id         → update item
DELETE /api/budget/items/:id         → soft-delete or hard-delete (implementer's choice)
```

Budget Summary (used by Overview tab and the persistent status bar):
```
GET /api/budget/summary?month=YYYY-MM
→ {
    monthly_cap,
    currency,
    spent_this_month,           // sum of cost where recurrence=MONTHLY + ONE_TIME items purchased this month
    recurring_monthly_total,    // sum of all MONTHLY items (what hits every month regardless)
    items_by_priority: {
      MANDATORY: { count, total },
      IMPORTANT: { count, total },
      OPTIONAL:  { count, total }
    },
    upcoming_one_time: BudgetItem[]   // one-time items not yet purchased, sorted by start_date
  }
```

**Read-only enforcement:**
- All `POST`, `PUT`, `DELETE` routes must return `403` if `req.readOnly === true`. This is handled by existing middleware — just confirm it is applied to all budget routes.

**Terraform / Infra:**
- No new AWS resources are required beyond what exists. If a new config table is added, add it to `terraform/budget.tf` and `variables.tf`.
- If a migration script is needed to normalise existing items, write it as a one-time Lambda or a standalone `scripts/migrate_budget.py` — do not run it inline on startup.

**Files touched (approximate):**
- `terraform/budget.tf`
- `backend/src/routes/budget.ts` (new or existing file)
- `backend/src/controllers/budgetController.ts` (new or existing)
- `backend/src/db/transforms.ts` (add budget item transforms)
- `packages/types/index.ts` (add `BudgetItem`, `BudgetConfig`, `BudgetSummary` types)

---

### BUD-02 · Overview Tab: Monthly Budget Status & Spending Summary
**Type:** Frontend  
**Parallel safety:** Owns the Overview tab component only. Does not touch Items, Timeline, or AI Advisor components.

#### User Stories
- As an athlete, I want to see my current month's spending versus my monthly cap so I know immediately if I'm on track.
- As an athlete, I want to set or update my monthly budget cap without navigating away.
- As a coach, I want to see an athlete's budget overview in a clean read-only view.

#### Background
The Overview tab currently exists but is unclear — it likely shows a raw summary without the budget cap context. This story rebuilds it as the first thing an athlete or coach sees when landing on the Budget page.

#### Acceptance Criteria

**Persistent budget status bar (above tabs, always visible when authenticated):**
- Shows: monthly cap (editable inline with a pencil icon), spent this month, remaining (or over-budget warning).
- "Edit cap" opens a small inline form (not a modal) — a number input + Save. Currency comes from the user's profile settings.
- On mobile, the bar collapses to two lines: `$450/month cap` on line 1, `Spent: $312 · Left: $138` on line 2.
- Over-budget state: text turns amber/orange; bar gets a subtle left border in that colour. Do not use red (red = pain log / injury in this app's visual language).
- If no cap is set, show a prompt: "Set a monthly cap to start tracking →" (tappable, opens the inline edit).

**Overview tab layout:**

Section 1 — This month's breakdown (3 summary tiles):
```
[ Mandatory: $180 ]  [ Important: $95 ]  [ Optional: $37 ]
```
Each tile shows the sum of purchased items in that tier this month. Tapping a tile filters the Items tab to that priority tier (pass via query param or shared state — not a full navigation).

Section 2 — Recurring costs panel:
- A compact table (not cards): Name | Category icon | Cost/month | Priority badge
- Footer row: "Total recurring monthly: $XXX"
- This is a read-only derived view — editing happens in the Items tab.

Section 3 — Upcoming one-time expenses:
- A compact list of `ONE_TIME` items not yet purchased, sorted by `start_date` ascending.
- Shows: name, estimated date, cost, priority badge.
- If `comp_linked=true`, show a small ⚡ icon next to the name.
- "No upcoming expenses" empty state if list is empty.

Section 4 — Monthly spend trend (last 6 months):
- A simple bar chart: one bar per month, bar height = total spent that month, a horizontal dashed line at the monthly cap.
- Bars coloured by status: under cap = muted brand colour, over cap = amber.
- If fewer than 2 months of data exist, replace the chart with a "Keep logging expenses to see your trend" placeholder. Do not show an empty chart.
- Use existing Recharts setup (the app already uses Recharts for other charts).

**Read-only state (coach view):**
- All of the above renders identically.
- "Edit cap" button and the inline form are hidden.
- A subtle banner at the top of the tab: "Viewing [Athlete Name]'s budget — read only."

**Mobile behaviour (≤480 px):**
- Status bar: 2-line compact layout (described above).
- The 3 priority tiles stack vertically.
- Recurring costs panel: show Name + Cost only, hide Category column.
- Trend chart: full width, 4 months instead of 6.

**Files touched:**
- `frontend/src/pages/BudgetPage.tsx` — add persistent status bar above tabs; wire up tab state
- `frontend/src/components/budget/BudgetOverview.tsx` — new component (Overview tab content)
- `frontend/src/components/budget/BudgetStatusBar.tsx` — new component (persistent bar)
- `frontend/src/api/` — add budget API client methods for `GET /api/budget/config`, `PUT /api/budget/config`, `GET /api/budget/summary`

---

### BUD-03 · Items Tab: Expense Table & Dynamic Entry Forms
**Type:** Frontend  
**Parallel safety:** Owns the Items tab component. Does not touch Overview, Timeline, or AI Advisor.

#### User Stories
- As an athlete, I want to add, edit, and delete expenses in a table that works like a spreadsheet so I don't have to context-switch into a heavy form.
- As an athlete, I want the form fields to adapt to what I'm adding — a gym membership doesn't need an exact date, but a meet entry does.
- As an athlete, I want to add any type of expense from one single entry point, not from six separate buttons.
- As a coach, I want to read the full expense list and understand each item's category and priority without being able to accidentally edit anything.

#### Background
The current UI has 6 add buttons, each spawning what appears to be the same form. Items render as large cards — unworkable on mobile. The core interaction model should shift to a **compact table with inline expansion**, similar to a spreadsheet or a Linear issue list.

#### Acceptance Criteria

**Table layout (desktop, >768 px):**

Columns (left to right):
```
[drag handle] · Priority badge · Category icon · Name · Recurrence icon · Cost · Date/Period · ⚡ comp · ✓ purchased · [actions ···]
```

- **Priority badge:** Small pill — `MANDATORY` (no fill, just border), `IMPORTANT` (filled, medium), `OPTIONAL` (faint/muted). Clicking it cycles through the three tiers inline without opening a form.
- **Category icon:** Icon-only with tooltip on hover (desktop) / label visible on expand (mobile). Use icons from Lucide React (already in the project).
- **Name:** Truncated to ~30 chars on table, full text on expand.
- **Recurrence icon:** Loop icon for recurring items, single dot for one-time.
- **Cost:** Right-aligned. Formatted with currency symbol.
- **Date/Period:** Smart display — recurring items show "Jan 2026 – Dec 2026" or "Jan 2026 – ongoing"; one-time shows "Jun 25, 2026" if exact or "Jun 2026" if month precision.
- **⚡ comp:** Visible only if `comp_linked=true`. Tap/hover shows the competition name.
- **✓ purchased:** A checkbox. Toggling it immediately PATCHes `purchased=true/false` + sets/clears `purchased_date` to today. No confirmation needed.
- **[actions ···]:** Kebab menu — Edit | Delete. Edit opens the row into an expanded inline form (see below). Delete asks for confirmation with item name ("Delete 'Creatine'?").

**Table layout (mobile, ≤768 px):**

The full table doesn't fit. Mobile shows a compact list row per item:
```
[ Priority badge ]  Name                           $85/mo
                    Category icon · Date range     [ ✓ ]
```
- Tapping the row opens an **inline expansion** (accordion, not a modal) showing all fields + edit/delete.
- The purchased checkbox remains visible in the collapsed row for quick toggle.

**Sorting and filtering (above the table):**
- A single compact filter bar with dropdown chips: Category (multi-select) | Priority (multi-select) | Recurrence | Comp-linked only | Show purchased.
- Default: all categories, all priorities, purchased items shown with a muted strikethrough style.
- On mobile, the filter bar collapses behind a "Filter" button with an active count badge.

**Adding a new item:**

Replace the 6 add buttons with a single **"+ Add expense"** button (top right on desktop; sticky FAB on mobile).

Clicking it inserts a new blank row at the top of the table and focuses the Name field. The row is in edit mode immediately — no modal.

**Dynamic form fields (inline row edit mode):**

The form adapts based on what's selected:

1. **Name** — always visible, free text.

2. **Category** — dropdown (all CategoryEnum values with icons). Selecting a category sets a **smart default** for Recurrence and Priority:
   - `competition_entry` → ONE_TIME, MANDATORY
   - `transport` → ONE_TIME, MANDATORY (if comp_linked)
   - `gym_membership` → MONTHLY, IMPORTANT
   - `supplement` → MONTHLY, OPTIONAL
   - `equipment` → ONE_TIME, IMPORTANT
   - `federation_membership` → ANNUAL, MANDATORY
   - `coaching` → MONTHLY, IMPORTANT
   - `food_comp_day` → ONE_TIME, MANDATORY (if comp_linked)
   
   These are defaults only — user can override.

3. **Recurrence** — dropdown (ONE_TIME / MONTHLY / QUARTERLY / ANNUAL).

4. **Cost** — number input with currency label (CAD, USD, etc. from user settings).

5. **Date fields (dynamic based on recurrence and date_precision toggle):**

   For **ONE_TIME**:
   - Toggle: "Exact date" ↔ "Month only" (defaults to "Exact date" for comp-linked, "Month only" for non-comp one-time purchases).
   - If "Exact date": a single date picker ("Purchase date or planned date").
   - If "Month only": a month/year picker (simpler — no day).

   For **MONTHLY / QUARTERLY / ANNUAL**:
   - Two month/year pickers: "Starts" and "Ends (blank = ongoing)".
   - No day-level precision — these are always month-scoped.

6. **Competition link (conditional):**
   - A toggle: "Tied to a competition?"
   - If toggled on, a dropdown appears listing the user's upcoming competitions (from `if-powerlifting-user-competitions`). Selecting one auto-populates the comp name.
   - Only show this toggle for categories where comp-linkage makes sense: `competition_entry`, `transport`, `accommodation`, `food_comp_day`, `food_weigh_in`. Hide it for `gym_membership`, `app_subscription`, etc.

7. **Priority** — 3-way toggle (MANDATORY / IMPORTANT / OPTIONAL). If comp_linked is true, default is MANDATORY (but still overridable).

8. **Notes** — optional single-line text. Shown at the bottom of the expanded row, collapsed behind a "Add note" link by default.

9. **Photo** — demoted to a secondary action ("Attach photo") at the very end, hidden by default. The S3 upload support is preserved but not front-and-centre.

**Save / Cancel in edit mode:**
- Save: checkmark button or pressing Enter from the last field. Optimistic UI — show saved state immediately, roll back on API error.
- Cancel: Escape key or × button. If a new unsaved row, it is removed. If editing existing, reverts to display mode.

**Empty state:**
- When the table has no items: a simple illustration-free message with one call to action: "No expenses yet. [+ Add your first expense]"

**Read-only state (coach view):**
- All rows render in display-only mode.
- "Add expense" button is hidden.
- Priority badge click-to-cycle is disabled.
- Purchased checkbox is visible but disabled (not clickable).
- No actions kebab menu.

**Files touched:**
- `frontend/src/components/budget/BudgetTable.tsx` — new component (main table)
- `frontend/src/components/budget/ExpenseRow.tsx` — new component (single table row, display + edit mode)
- `frontend/src/components/budget/ExpenseForm.tsx` — new component (inline form fields, used inside ExpenseRow)
- `frontend/src/pages/BudgetPage.tsx` — wire Items tab to BudgetTable
- `frontend/src/api/` — add item CRUD client methods

---

### BUD-04 · Timeline Tab: Visual Spend Calendar Anchored to Competition Dates
**Type:** Frontend (+ read from existing competition data)  
**Parallel safety:** Owns the Timeline tab component only. Reads competitions from existing competition store (does not write to it).

#### User Stories
- As an athlete, I want to see a month-by-month visual of when each expense hits so I can plan my cash flow around competition dates.
- As a coach, I want to quickly see whether the athlete has clustered too many large expenses around comp week so I can flag it.

#### Background
The app already knows the athlete's competition dates (stored in `if-powerlifting-user-competitions`, accessible via the existing competitions store/API). The timeline should treat competition dates as anchors and plot expenses relative to them.

#### Acceptance Criteria

**Layout: vertical month-by-month scroll (mobile-first)**

Each month is a "row" or "band":

```
─── January 2026 ──────────────────── $170 ───────────────────────
  [⚡ CPU Meet Entry]       MANDATORY   $75     one-time   Jan 2026
  [🔁 Fortis Fitness]      IMPORTANT   $85     monthly    ← recurring
  [• Pre-workout]          OPTIONAL    $35     one-time

─── February 2026 ──────────────────── $85 ────────────────────────
  [🔁 Fortis Fitness]      IMPORTANT   $85     monthly    ← recurring

─── ⚡ COMPETITION: CPU Ottawa Open ── Mar 15, 2026 ──────────────
  (highlighted band, distinct background colour)
─── March 2026 ─────────────────────── $340 ───────────────────────
  [⚡ Hotel]                MANDATORY   $180    one-time
  [⚡ Transport]            MANDATORY   $60     one-time
  [⚡ Comp day food]        MANDATORY   $25     one-time
  [🔁 Fortis Fitness]      IMPORTANT   $85     monthly
```

Design rules:
- **Recurring items** appear in every month they are active. They are rendered in a slightly muted style with a "🔁 recurring" label so the user understands they are not duplicated — it's the same item appearing each month.
- **Competition dates** appear as a full-width highlight band between months (amber/yellow border, subtle background tint). The competition name is shown in the band.
- **Month total** is shown right-aligned in the month header row. If the total exceeds `monthly_cap`, the total turns amber.
- Items within each month are sorted: MANDATORY first, then IMPORTANT, then OPTIONAL.

**Navigation:**
- Default scroll position: current month, or the next upcoming competition month if within 3 months.
- A sticky mini-nav at the top of the tab: `< Jan 2026 | Feb | Mar ⚡ | Apr | May >` — pill buttons for each month in the program window (from the earliest start_date in the item set through 2 months past the latest end_date or competition). Tapping a pill scrolls to that month.
- On desktop, months are shown in a 2-column grid layout instead of a single-column scroll.

**Filters:**
- Same compact filter bar pattern as BUD-03 (Priority | Category | Comp-linked only). Filter state is independent from the Items tab filter state.

**Empty state:**
- If no items and no competitions: "Add expenses in the Items tab and link a competition in the Designer to see your timeline."
- If items exist but no competitions: show the timeline without competition bands; display a soft prompt "Link a competition in the Designer to anchor your timeline."

**Read-only state:**
- Timeline renders identically for coaches. No edit controls on any item (items are display-only here even in athlete mode — editing happens in the Items tab).

**Files touched:**
- `frontend/src/components/budget/BudgetTimeline.tsx` — new component
- `frontend/src/pages/BudgetPage.tsx` — wire Timeline tab
- Reads from: existing competition store or `GET /api/competitions` (no new backend routes needed)
- Reads from: `GET /api/budget/items` (already defined in BUD-01)

---

### BUD-05 · AI Advisor Tab: Budget Triage & Pre-Comp Priority Analysis
**Type:** Frontend + Backend AI  
**Parallel safety:** Owns the AI Advisor tab component and a new AI backend endpoint. Does not touch Overview, Items, or Timeline components. Follows the existing `invokeToolDirect → IF Agent API → specialist tool` pattern used everywhere else in the app.

#### User Stories
- As an athlete over my monthly budget, I want the AI to tell me which optional expenses I can drop without affecting my competition performance.
- As an athlete preparing for a competition, I want the AI to look at my current expense list and flag anything I might be missing (e.g., "You have no hotel booked for your March meet").
- As a coach, I want to see the AI's budget assessment so I can align with my athlete on priorities before our next check-in.

#### Background
The app already has 10+ AI surfaces following the same pattern: frontend makes a call to an Express route, which calls `invokeToolDirect`, which calls the IF Agent API with a specialist tool. Budget is the one analytics section with no AI surface. This story adds one.

The AI surface should follow the same "cache-only by default, refresh on demand" pattern used for `correlation` and `program-evaluation` on the Analysis page — the AI does not regenerate on every page load.

#### Acceptance Criteria

**Tab layout:**

The AI Advisor tab has two states:

**State A — No analysis generated yet (or cache expired):**
```
┌────────────────────────────────────────────────────────┐
│  AI Budget Advisor                                      │
│                                                         │
│  Get an AI-powered breakdown of your budget priorities  │
│  and a pre-comp cutlist if you're over your cap.        │
│                                                         │
│  [ Analyse my budget ]                                  │
│                                                         │
│  Analysis looks at: your monthly cap, current items,    │
│  their priorities, and your upcoming competition dates. │
└────────────────────────────────────────────────────────┘
```

**State B — Analysis available (from cache or just generated):**

The output is a structured panel, not a freeform chat bubble. The AI is instructed to return structured JSON that the frontend renders:

```
Section 1: Overall assessment
  – One sentence summary: "You're $47 over your monthly cap with your CPU Ottawa Open in 6 weeks."

Section 2: What's locked in (MANDATORY items)
  – List of MANDATORY items with a ✓ icon. Brief AI note on each if relevant.
  – E.g., "Meet entry — ✓ Already purchased." / "Transport — ⚠ Not marked as purchased yet."

Section 3: Suggested cuts (if over budget)
  – Ordered list of OPTIONAL items recommended for cutting, with reason.
  – E.g., "1. Ashwagandha ($40) — Minimal performance impact 6 weeks out. Consider dropping."
  – E.g., "2. Meal prep service ($80) — You can prepare food yourself during the taper week."
  – Each suggestion has a one-tap "Mark as cut" action → this toggles the item to a new visual state (strikethrough in the Items tab), it does NOT delete it.

Section 4: Gaps identified
  – Items the AI thinks are missing based on the competition date and existing items.
  – E.g., "⚠ No hotel expense found for your Ottawa meet (Mar 15). If you're travelling, add it."
  – E.g., "⚠ No post weigh-in food logged. This is important for performance if you're cutting weight."

Section 5: Coach note (if the viewing user is the coach)
  – A short paragraph framed for the coach: "Things to discuss with [athlete] in your next session."
  – This section is hidden when viewed by the athlete themselves.
```

**AI call details (for the backend implementer):**

The backend route should:
1. Fetch the user's `BudgetConfig` and all `BudgetItem[]`.
2. Fetch the user's upcoming competitions from `if-powerlifting-user-competitions`.
3. Assemble a structured context payload and pass it to `invokeToolDirect` targeting the `/powerlifting_coach` specialist.
4. Instruct the model to return JSON only (no markdown prose) matching the structure above — the frontend renders it, the model does not format it.
5. Cache the result in `if-powerlifting-analysis-cache` with a 48-hour TTL (shorter than the 7-day used elsewhere, since budget data changes frequently).
6. A `refresh=true` param forces regeneration and re-caches.

**Prompt contract (PM-level, not literal prompt text):**
The AI must be told:
- The athlete's monthly cap and current total spend.
- Every budget item: name, category, priority tier, cost, recurrence, comp_linked status, whether purchased.
- The list of upcoming competitions with dates.
- The comp is the absolute priority — MANDATORY comp-linked items are never suggested for cuts.
- Suggestions should be brief, practical, and sport-appropriate (a powerlifting coach's voice, not a generic financial advisor's).
- The output must be JSON that matches the Section 1–5 schema above. Field names must be stable (the frontend depends on them).

**UI interactions:**
- "Analyse my budget" button: spinner while generating (average 5–15 seconds based on other AI surfaces in the app). Show a subtle "Analysing your expenses and upcoming meets…" status message.
- "Refresh analysis" link (small, below the generated result): regenerates. Asks "Regenerate analysis? This will replace the current result." before proceeding.
- "Mark as cut" in Section 3: immediately PATCHes the item with a `cut_by_ai: true` flag (add to BudgetItem schema) and shows a strikethrough on that item in the Items tab. A "Restore" link appears in the Items tab row.
- If the athlete has no monthly cap set, the "Analyse my budget" button shows a tooltip: "Set a monthly cap first (Overview tab)."

**Read-only state (coach view):**
- All analysis renders normally.
- "Analyse my budget" and "Refresh analysis" buttons are hidden — coaches cannot trigger new AI runs on an athlete's account.
- Section 5 (Coach note) is visible only to coaches.

**New backend route:**
```
POST /api/budget/ai-analysis?refresh=true|false
→ structured JSON per Section 1–5 schema above
```

**Files touched:**
- `frontend/src/components/budget/AiBudgetAdvisor.tsx` — new component
- `frontend/src/pages/BudgetPage.tsx` — wire AI Advisor tab
- `frontend/src/api/` — add `POST /api/budget/ai-analysis` client method
- `backend/src/routes/budget.ts` — add `/ai-analysis` route
- `backend/src/controllers/budgetController.ts` — add AI analysis handler
- `packages/types/index.ts` — add `BudgetAiAnalysis` response type; add `cut_by_ai` field to BudgetItem

---

## Cross-cutting Concerns (all stories must respect)

### Mobile-first constraints
- Target the smallest viable viewport: **375 px wide** (iPhone SE).
- No horizontal scroll ever — if a table column doesn't fit, it is hidden on mobile and shown on expand.
- Touch targets: minimum 44×44 px for any tappable element (Apple HIG).
- Sticky FAB (floating action button) for "+ Add expense" on mobile — positioned bottom-right, does not overlap table content.
- Font size: never below 14 px for body text on mobile.

### Read-only / auth guard
- The existing `readOnly` prop/flag is the mechanism. Every new component must accept and respect a `readOnly: boolean` prop.
- If `readOnly=true`: all write actions (add, edit, delete, purchased toggle, AI generate) are visually hidden or disabled.
- Unauthenticated users land on a "Sign in to view your budget" prompt. Do not render the page with dummy data.

### Optimistic UI
- Purchased checkbox toggle, priority badge cycle, and "mark as cut" should apply immediately in UI and sync in the background. Roll back with a toast error if the API fails.

### Currency
- All amounts are stored in the user's currency (from profile settings). The currency symbol is shown consistently — do not show raw numbers without units.
- Do not build a currency converter. If the user's currency is unknown, default to displaying the raw number with no symbol and a soft prompt to set currency in profile settings.

### Existing visual language
- Use the existing Mantine 9 component set, Tailwind utilities, and colour tokens from the app.
- Priority badge colours should not conflict with existing badges in the app (RPE, set status). Use: MANDATORY = brand accent (existing), IMPORTANT = neutral/blue, OPTIONAL = muted grey.
- Comp-linked ⚡ icon: use `Zap` from Lucide React (already in the dependency).

---

## Out of Scope (do not implement)

- Receipt scanning or OCR.
- Bank or credit card integrations.
- Multi-currency conversion.
- Budget sharing via a public link (future roadmap).
- Push notifications for budget threshold alerts (future roadmap).
- The "Federation memberships" tab in the current UI is **removed** — federation memberships are a category in the Items table.

---

## Definition of Done (all stories)

- [ ] All acceptance criteria in the story are met.
- [ ] The feature renders correctly at 375 px, 768 px, and 1280 px widths.
- [ ] Read-only mode is enforced — a coach or unauthenticated user cannot trigger any write operation.
- [ ] No TypeScript errors in the affected files.
- [ ] Existing Budget page route is not broken.
- [ ] API errors are handled gracefully — the UI shows a toast or inline error, not a blank screen or console error.
