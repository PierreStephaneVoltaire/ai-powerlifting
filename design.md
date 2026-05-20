# Powerlifting App — Design Spec

## What's Wrong Right Now

---

## Design Direction

**What to change:** Typography hierarchy, color system, spatial density, and state communication (fatigue, completion, intensity).

---

## Color System

Define these as Mantine `cssVariablesResolver` tokens:

```ts
// mantine.config.ts
export const theme = createTheme({
  primaryColor: 'blue',
  colors: {
    // extend with custom palette
  }
});
```

| Token | Value | Usage |
|---|---|---|
| `--bg-base` | `#090b10` | App background (deeper black, not flat gray) |
| `--bg-surface` | `#111318` | Card backgrounds |
| `--bg-elevated` | `#181b24` | Modals, drawers, input fills |
| `--bg-hover` | `#1e2230` | Row hover states |
| `--border-subtle` | `#1f2335` | Card borders |
| `--border-default` | `#2a2f45` | Input borders, dividers |
| `--accent-blue` | `#3b82f6` | Primary CTA, links, active states |
| `--accent-blue-dim` | `#1e3a5f` | Selected row backgrounds, badge fills |
| `--text-primary` | `#e2e6f0` | Main content |
| `--text-secondary` | `#8891aa` | Labels, metadata |
| `--text-muted` | `#4a5068` | Placeholders, disabled |
| `--fatigue-low` | `#22c55e` | < 40% fatigue |
| `--fatigue-mid` | `#f59e0b` | 40–65% fatigue |
| `--fatigue-high` | `#ef4444` | > 65% fatigue |
| `--lift-squat` | `#6366f1` | Squat accent (indigo) |
| `--lift-bench` | `#3b82f6` | Bench accent (blue) |
| `--lift-deadlift` | `#f97316` | Deadlift accent (amber-orange) |

The per-lift colors are high-value: use them consistently across every surface where lift type appears (progress bars, session row borders, chart lines). One color = one lift everywhere.

---

## Typography

Replace whatever you're using now with this pairing. Import from Google Fonts or self-host.

```css
/* Display + key numbers */
font-family: 'Barlow Condensed', sans-serif;
font-weight: 600–700;
letter-spacing: -0.02em;

/* Body + labels */
font-family: 'DM Sans', sans-serif;
font-weight: 400–500;

/* Monospace numbers (weights, RPE, lb values) */
font-family: 'IBM Plex Mono', monospace;
font-weight: 400;
```

**Barlow Condensed** for big numbers and section headers gives an athletic, technical feel without being gimmicky. **IBM Plex Mono** for all numeric data (weights, RPE, percentages) creates instant visual separation between data and labels — readers can scan faster.

### Type Scale (Mantine headings override)

| Role | Font | Size | Weight |
|---|---|---|---|
| Hero metric (e.g. `168.6 lb`) | IBM Plex Mono | 36–48px | 400 |
| Section header | Barlow Condensed | 18px | 600 |
| Card title | DM Sans | 13px | 500, uppercase, ls: 0.08em |
| Body / row text | DM Sans | 13–14px | 400 |
| Label / meta | DM Sans | 11px | 400, `--text-secondary` |

---

## Component Specs

### 1. Sidebar Nav

**Current problems:** No depth, no active state differentiation, icon + label spacing feels cramped.

```
Width: 200px (expanded), 56px (collapsed — consider adding this)
Background: --bg-surface with a 1px right border at --border-subtle

Nav item (inactive):
  padding: 8px 16px
  border-radius: 6px
  color: --text-secondary
  icon: 16px, color: --text-muted

Nav item (active):
  background: --accent-blue-dim
  left border: 2px solid --accent-blue (use a Box with borderLeft, not outline)
  color: --text-primary
  icon: --accent-blue

Nav item (hover):
  background: --bg-elevated
  color: --text-primary
  transition: 120ms ease
```

Add a subtle `VERSION` badge at the bottom (you already have `13.0` at the top — move it here, make it smaller).

---

### 2. Dashboard Cards

**Current problems:** Every card looks the same. The grid breaks below 1200px. Important numbers aren't dominating.

**Card base:**
```css
background: var(--bg-surface);
border: 1px solid var(--border-subtle);
border-radius: 10px;
padding: 20px 24px;
```

**No box-shadow.** Box shadows on dark themes look muddy. Use border only.

**Hero metric cards** (Body Weight, Fatigue State, Total):
- The primary number should be `48px / IBM Plex Mono / --text-primary`
- The label should be `11px / DM Sans uppercase / --text-secondary`
- The number should be the first thing your eye lands on

**Progress bars** (Actual Maxes):
- Height: `6px` minimum, prefer `8px`
- Use lift-specific colors: squat = `--lift-squat`, bench = `--lift-bench`, deadlift = `--lift-deadlift`
- Add the percentage fill as a subtle text label on the right: `90%`
- Mantine `Progress` component with `color` prop set per lift

**Fatigue State card:**
- The `47%` number should use dynamic color: `--fatigue-mid` at 47%
- The colored badge pills (MEAN 40%, PEAK 62%) are good — keep them but make them `height: 20px` with `border-radius: 4px`

**Upcoming Competitions:**
- CONFIRMED vs OPTIONAL should use color, not just text: green pill vs gray pill
- The countdown (`51d`) should be right-aligned and use IBM Plex Mono

```

Use Mantine `SimpleGrid` with `breakpoints` prop.

---

### 3. Sessions List (agenda view)

**Current problems:** Completely flat. Phase info is undersold. No visual rhythm.

**Week header:**
```css
padding: 8px 0 6px 0;
font: 11px DM Sans, uppercase, letter-spacing: 0.1em;
color: --text-muted;
border-bottom: 1px solid --border-subtle;
margin-bottom: 4px;
position: sticky;
top: 48px; /* below topbar */
background: --bg-base;
z-index: 10;
```

**Session row (agenda):**
```css
padding: 12px 16px;
border-radius: 8px;
background: --bg-surface;
border: 1px solid --border-subtle;
margin-bottom: 4px;

/* Left border color-coded by phase */
border-left: 3px solid <phase-color>;
```



**Row layout:**
```
[date col 80px] [phase badge] [exercise list — flex-grow] [right: "3 exercises / RPE 7"] [checkmark if done]
```

The date should be IBM Plex Mono. The exercise names should be `--text-secondary` (not primary — they're context, not the headline).

**Hover state:**
```css
background: --bg-hover;
border-color: --border-default;
cursor: pointer;
transition: 120ms ease;
```

---

### 4. Session Detail (Workout Cards)

**Current problems:** Exercise cards feel like generic form containers. Everything is the same visual weight. The sets-completion dots are too small to tap on mobile.

**Session header (sticky):**
```
height: 48px
background: --bg-surface / blur backdrop
border-bottom: 1px solid --border-subtle
Contains: date, phase badge, ← back button
position: sticky, top: 0
```

**Exercise card:**
```css
background: --bg-surface;
border: 1px solid --border-subtle;
border-radius: 10px;
padding: 0; /* use inner sections instead */

/* Header strip */
.exercise-header {
  padding: 12px 16px;
  border-bottom: 1px solid --border-subtle;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Exercise name */
font: 15px DM Sans, weight 500, --text-primary

/* Data row */
.exercise-inputs {
  padding: 12px 16px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr; /* Sets / Reps / lb / RPE */
  gap: 8px;
}
```

**Input fields (Sets, Reps, lb, RPE):**
- Label: `10px, uppercase, --text-muted` above the input
- Input: `height: 44px minimum` (touch target), `font: IBM Plex Mono 15px`, `text-align: center`
- Background: `--bg-elevated`, border: `--border-default`
- On focus: border becomes `--accent-blue`

**Sets completion dots:**
- Current size is too small. Change to `20px × 20px` circles
- Incomplete: `border: 2px solid --border-default`, background: transparent
- Complete: `background: --fatigue-low`, no border
- Tappable on mobile — use `min-width: 44px, min-height: 44px` hit area even if visual is smaller

**Notes textarea:**
```css
background: transparent;
border: 1px solid --border-subtle;
border-radius: 6px;
font: 13px DM Sans, --text-secondary;
padding: 8px 12px;
resize: none;
min-height: 36px;
```
Only show it if it has content, or on tap (collapsed by default on mobile).

**Drag handle:**
The `⠿` drag handle on the left of each exercise is useful but visually lost. Make it `color: --text-muted` and give it a `6px` left padding that changes to `--text-secondary` on hover.

**Bottom action bar (Discard / Save / Done):**
```css
position: sticky;
bottom: 0;
background: --bg-base;
border-top: 1px solid --border-subtle;
padding: 12px 16px;
display: flex;
justify-content: flex-end;
gap: 8px;
```
This is already done-ish but should be sticky at the bottom on mobile — make sure it's not getting scrolled away.

---

### 5. Settings Drawer

**Current problems:** Pure Mantine defaults. Nothing wrong, just no character.

The drawer is fine structurally. Three targeted fixes:

1. **Section labels:** Add `11px uppercase letter-spacing: 0.1em --text-muted` headers above each group (Account, Appearance, Preferences). Mantine `Text` with `tt="uppercase" size="xs" c="dimmed"`.

2. **Toggle groups (Light/Dark/System, Male/Female):** The current segmented controls look fine but bump the height to `36px` and make the selected state use `--accent-blue-dim` background + `--accent-blue` text instead of pure white.

3. **Spacing:** Add `24px` gap between each settings section using Mantine `Stack spacing="xl"`.

---

## Mobile Priorities

You said mobile is especially painful. In priority order:

1. **Session detail inputs** — 44px touch targets on all inputs/buttons. The `grid-template-columns: 1fr 1fr 1fr 1fr` layout works at 375px if you drop it to `1fr 1fr` (two rows: Sets+Reps, lb+RPE).

2. **Bottom sticky bar** — `Discard / Save / Done` must always be visible without scrolling. Use `position: fixed, bottom: 0` with `padding-bottom: env(safe-area-inset-bottom)` for iOS.

3. **Sessions list** — rows are fine on mobile. Just make the tap target `min-height: 52px`.




---

## Quick Wins (do these first, < 1 day each)

1. Set `--bg-base: #090b10` and `--bg-surface: #111318` in your Mantine theme — immediate depth improvement
2. Add IBM Plex Mono to all numeric values (`lb`, `RPE`, `%`) via a shared `<Num>` component that wraps `<Text ff="monospace">`
3. Add `border-left: 3px solid <phase-color>` to session rows — transforms the sessions list instantly
4. Bump all input heights to `44px` — fixes mobile immediately
5. Make the `47%` fatigue number use `color: var(--fatigue-mid)` dynamically

---
