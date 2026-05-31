# Directives Portal — Frontend UI Migration Plan

Match the directives portal frontend exactly to the powerlifting app stack: same Mantine setup,
same CSS token system, same dark theme, no Tailwind in component JSX.

Reference app: `utils/powerlifting-app/frontend/`
Target app:    `utils/directives-portal/frontend/`

---

## What is wrong right now

| Area | Directives Portal (broken) | Powerlifting App (target) |
|---|---|---|
| `postcss.config.js` | ~~Missing `postcss-preset-mantine`~~ ✅ fixed | Has both — bundles Mantine styles + fonts locally |
| `index.css` imports | `@import 'tailwindcss/base'` old syntax | `@import '@mantine/core/styles.css'` then `@tailwind` directives |
| `index.css` tokens | Only tier colors defined. No `--bg-base`, `--border-*`, `--accent-*`, `--status-*` | Full token set in `:root` and `.dark` blocks |
| `index.css` body rule | No `background: var(--bg-base)` → body stays white | `background: var(--bg-base); color: var(--text-primary)` — this is what makes dark mode dark |
| `index.css` Mantine overrides | None | `--mantine-color-body`, `--mantine-color-text` etc. bound to CSS vars |
| `main.tsx` cssVariablesResolver | Only 7 tokens — missing all `--border-*`, `--accent-*`, `--status-*` | Full token set per light/dark |
| `DirectiveCard.tsx` | Tailwind classes in JSX: `bg-white`, `dark:bg-[...]`, `rounded-lg`, `shadow-sm`, `ring-2` | Pure Mantine `style` prop + `var()` CSS tokens, zero Tailwind in JSX |
| `DirectivesPage.tsx` header | Hardcoded inline style objects, raw `fontFamily` string literals | CSS var refs and Mantine `ff` props |
| Modals | Default unstyled Mantine modals | `classNames` prop with `if-designer-modal-*` CSS classes |

---

## Step 1 — `postcss.config.js` ✅ ALREADY DONE

No further changes needed.

---

## Step 2 — `src/index.css` (highest leverage — fixes dark mode)

File: `utils/directives-portal/frontend/src/index.css`

Replace the ENTIRE file. Copy `utils/powerlifting-app/frontend/src/index.css` as the base,
then make these directives-specific adjustments:

1. Keep the tier color vars (`--tier-0-bg` through `--tier-5-border`) in `:root` and `.dark`
   - these are directives-specific and not in the powerlifting app
2. Rename `--accent-blue` / `--accent-blue-dim` to `--accent-violet` / `--accent-violet-dim`
   with values `#7c3aed` / `#ede9fe` (light) and `#7c3aed` / `#1e1a3f` (dark)
3. Remove all powerlifting-specific CSS classes that reference session/exercise/calendar/chart
   UI patterns (`if-session-*`, `if-exercise-*`, `if-calendar-*`, `if-dashboard-*`,
   `if-designer-sess-*`, `if-supp-*`, `if-lift-*`, `if-video-*`, `rbc-*`)
4. KEEP these shared classes (copy verbatim from powerlifting):
   - `@layer base` block (body rule with `background: var(--bg-base)` — critical)
   - `:root, [data-mantine-color-scheme]` Mantine override block
   - `.mantine-Paper-root`, `.mantine-Card-root` overrides
   - All `.mantine-Input-input` / `.mantine-TextInput-input` etc. overrides
   - `.mantine-Popover-dropdown` / `.mantine-Menu-dropdown` overrides
   - `.if-page-header`, `.if-page-title`, `.if-page-subtitle`
   - `.if-small-label`
   - `.if-card`, `.if-list-row`
   - `.if-pill`, `.if-pill-info`, `.if-pill-success`, `.if-pill-warning`, `.if-pill-danger`, `.if-pill-neutral`
   - `.if-designer-modal-content`, `.if-designer-modal-header`, `.if-designer-modal-title`, `.if-designer-modal-body`, `.if-designer-modal-foot`
   - `.if-mock-card`, `.if-mock-header`, `.if-mock-title`, `.if-mock-subtitle`
   - `::-webkit-scrollbar` block
   - `--color-background-*` / `--color-text-*` / `--color-border-*` alias vars in `:root` and `.dark`
   - All `--status-*` vars in `:root` and `.dark`
   - `--font-sans`, `--font-mono`, `--border-radius-md`, `--border-radius-lg` in `:root`

The body rule is the most critical change:
```css
body {
  @apply bg-background text-foreground;
  background: var(--bg-base);         /* <— this line makes dark mode actually paint dark */
  color: var(--text-primary);
  font-family: 'DM Sans', sans-serif;
  font-feature-settings: "rlig" 1, "calt" 1;
  overflow-x: hidden;
}
```

---

## Step 3 — `src/main.tsx`

File: `utils/directives-portal/frontend/src/main.tsx`

Two changes:

### 3a. Remove duplicate Mantine CSS imports

Delete these lines — they already live in `index.css` and must not be imported twice:
```tsx
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
```

### 3b. Expand cssVariablesResolver

Replace the existing resolver with the full token set. Keep `primaryColor: 'violet'`.

```tsx
const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--mantine-color-violet-6': '#7c3aed',
    '--accent-violet': '#7c3aed',
  },
  light: {
    '--bg-base': '#f6f8fb',
    '--bg-surface': '#ffffff',
    '--bg-elevated': '#f1f5f9',
    '--bg-hover': '#eaf0ff',
    '--border-subtle': '#e2e8f0',
    '--border-default': '#cbd5e1',
    '--accent-violet-dim': '#ede9fe',
    '--text-primary': '#111827',
    '--text-secondary': '#526071',
    '--text-muted': '#94a3b8',
  },
  dark: {
    '--bg-base': '#090b10',
    '--bg-surface': '#111318',
    '--bg-elevated': '#181b24',
    '--bg-hover': '#1e2230',
    '--border-subtle': '#1f2335',
    '--border-default': '#2a2f45',
    '--accent-violet-dim': '#1e1a3f',
    '--text-primary': '#e2e6f0',
    '--text-secondary': '#8891aa',
    '--text-muted': '#4a5068',
  },
})
```

---

## Step 4 — `src/components/DirectiveCard.tsx`

File: `utils/directives-portal/frontend/src/components/DirectiveCard.tsx`

Remove all Tailwind classes from the outer `Box`. Replace with pure `style` prop:

```tsx
// BEFORE — has Tailwind classes
<Box
  ref={setNodeRef}
  style={style}
  className={`
    bg-white dark:bg-[var(--bg-surface)]
    border border-[var(--tier-${directive.alpha}-border,--border-default)]
    rounded-lg p-3 shadow-sm
    ${isDragging ? 'shadow-xl ring-2 ring-violet-400' : ''}
  `}
>

// AFTER — pure style prop, no Tailwind
<Box
  ref={setNodeRef}
  style={{
    ...style,
    background: 'var(--bg-surface)',
    border: `0.5px solid var(--tier-${directive.alpha}-border, var(--border-subtle))`,
    borderRadius: 'var(--border-radius-lg)',
    padding: 12,
    boxShadow: isDragging ? '0 8px 24px rgba(0,0,0,0.2)' : 'none',
    outline: isDragging ? '2px solid var(--mantine-color-violet-5)' : 'none',
    transition: 'background 120ms ease, border-color 120ms ease',
  }}
>
```

---

## Step 5 — `src/pages/DirectivesPage.tsx`

File: `utils/directives-portal/frontend/src/pages/DirectivesPage.tsx`

### 5a. Logo box
```tsx
// BEFORE
<Box style={{ width: 32, height: 32, borderRadius: 8,
  background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
  display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
  <Shield size={18} color="white" />
</Box>
<Text fw={700} size="lg" style={{ fontFamily: "'Barlow Condensed', sans-serif" }}>
  IF Directives
</Text>

// AFTER
<Box style={{ width: 32, height: 32, borderRadius: 8,
  background: 'var(--mantine-color-violet-6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
  <Shield size={18} color="white" />
</Box>
<Text fw={600} size="lg" ff="var(--font-sans)" c="var(--text-primary)">
  IF Directives
</Text>
```

### 5b. Error box
```tsx
// BEFORE
<Box mb="md" p="sm" style={{ background: 'var(--mantine-color-red-0)', borderRadius: 8,
  border: '1px solid var(--mantine-color-red-5)' }}>

// AFTER
<Box mb="md" p="sm" style={{ background: 'var(--status-danger-bg)', borderRadius: 8,
  border: '0.5px solid var(--status-danger-border)' }}>
```

---

## Step 6 — Modal classNames

Files:
- `utils/directives-portal/frontend/src/components/DirectiveDetailModal.tsx`
- `utils/directives-portal/frontend/src/components/NewDirectiveModal.tsx`

Add `classNames` to every `<Modal>` component:

```tsx
<Modal
  // ...existing props...
  classNames={{
    content: 'if-designer-modal-content',
    header: 'if-designer-modal-header',
    title: 'if-designer-modal-title',
    body: 'if-designer-modal-body',
  }}
>
```

---

## Step 7 — Verify no Tailwind classes remain in component JSX

After Steps 4–5, run this grep. Must return zero hits:

```bash
grep -rn 'className=' utils/directives-portal/frontend/src/components/ utils/directives-portal/frontend/src/pages/
```

Any remaining `className` on a component Box/div that contains Tailwind utility names
(`bg-`, `text-`, `border-`, `rounded-`, `shadow-`, `ring-`, `p-`, `px-`, `py-`, `flex-`)
must be replaced with a `style` prop.

---

## Step 8 — Build verification

```bash
cd utils/directives-portal/frontend
npm run build
npm run typecheck
```

Both must pass with zero errors.

The CSS bundle should be ~520KB+ (Mantine styles bundled locally).

The built `dist/index.html` must NOT reference Google Fonts:
```bash
grep -i 'googleapis' utils/directives-portal/frontend/dist/index.html
# must return nothing
```

---

## Files changed summary

| File | Change |
|---|---|
| `frontend/src/index.css` | Full rewrite — copy powerlifting base, keep tier vars, rename accent tokens |
| `frontend/src/main.tsx` | Remove duplicate CSS imports, expand cssVariablesResolver |
| `frontend/src/components/DirectiveCard.tsx` | Remove Tailwind classes, replace with `style` prop + CSS vars |
| `frontend/src/pages/DirectivesPage.tsx` | Replace hardcoded inline styles in header and error box |
| `frontend/src/components/DirectiveDetailModal.tsx` | Add `classNames` to `<Modal>` |
| `frontend/src/components/NewDirectiveModal.tsx` | Add `classNames` to `<Modal>` |

**Files NOT changed (correct as-is):**
- `frontend/src/App.tsx`
- `frontend/src/auth/AuthProvider.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/AuthCallbackPage.tsx`
- `frontend/src/store/directivesStore.ts`
- `frontend/src/api/client.ts`
- `frontend/src/components/TierColumn.tsx` (already uses CSS vars correctly)
- `frontend/src/components/TypeBadge.tsx` (pure Mantine, no Tailwind)
- `frontend/postcss.config.js` ✅ already fixed
- All backend files ✅ already fixed
