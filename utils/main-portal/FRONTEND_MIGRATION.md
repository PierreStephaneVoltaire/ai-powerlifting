# Main Portal — Frontend UI Migration Plan

Bring the main portal frontend fully onto the powerlifting app stack: Mantine v9,
same CSS token system, same dark theme, no manual dark mode toggle, no raw HTML
elements, no Tailwind class names in component JSX.

Reference app: `utils/powerlifting-app/frontend/`
Target app:    `utils/main-portal/frontend/`

---

## What is wrong right now

| Area | Main Portal (broken) | Powerlifting App (target) |
|---|---|---|
| UI framework | No Mantine at all — raw `<div>`, `<h1>`, `<a>` with Tailwind classes | Mantine v9 throughout |
| Styling approach | 100% Tailwind utility classes in every component and page | Pure Mantine components + CSS var tokens. Zero Tailwind in JSX |
| Dark mode | Manual `darkMode` state in `App.tsx`, `localStorage`, `document.documentElement.classList.add('dark')` | `MantineProvider defaultColorScheme="auto"` — reads `prefers-color-scheme`, no manual toggle needed |
| `package.json` | Missing `@mantine/core`, `@mantine/notifications`, `@mantine/hooks`. React 18 (`^18.3.1`) | Mantine v9, React 19, `lucide-react` |
| `postcss.config.js` | Only `tailwindcss` + `autoprefixer` — missing `postcss-preset-mantine`, `postcss-simple-vars` | Has all four |
| `index.css` | Plain Tailwind base + minimal CSS vars. No `--bg-base`, no `background: var(--bg-base)` on body | Full token set, `background: var(--bg-base)` on body |
| `main.tsx` | No `MantineProvider`, no `cssVariablesResolver`, no `createTheme` | Full Mantine setup with theme + resolver |
| `App.tsx` | Raw `<div className="min-h-screen bg-background">` layout with hardcoded toggle button | `AppShell` or plain Mantine layout wrapper, color scheme from provider |
| `Hub.tsx` | Every section uses Tailwind grid/spacing classes (`space-y-6`, `grid grid-cols-1 md:grid-cols-2`, etc.) | Mantine `Stack`, `SimpleGrid`, `Group`, `Text`, `Title` |
| `PortalCard.tsx` | Raw `<div>` with `className="group block p-4 rounded-lg border ..."` | Mantine `Paper` or CSS-var card class (`if-list-row` / `if-card` pattern) |
| `SnapshotBar.tsx` | Raw `<div>` with Tailwind flex/gap/border classes, `text-green-600 dark:text-green-400` hardcoded colors | CSS var `--status-success-text` / `--status-danger-text` tokens |
| `AlertsList.tsx` | Raw `<div>` with `bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800` — hardcoded dark variant classes | CSS var `--status-success-*` / `--status-warning-*` tokens |
| `SignalStrip.tsx` | Raw `<div>` with `bg-muted`, Tailwind color classes from `formatters.ts` returning Tailwind class strings | CSS var tokens, Mantine `Badge`/`Text` with `c=` and `bg=` props |
| `formatters.ts` | Returns Tailwind class name strings (`'text-green-600 dark:text-green-400'`) — tightly coupled to Tailwind | Returns semantic values (color tokens or status strings) that components map to CSS vars |
| CSP | No CSP meta tag in `index.html` | CSP meta tag matching the gateway snippet |

---

## Step 1 — `package.json`

File: `utils/main-portal/frontend/package.json`

Add Mantine, bump React to 19, add lucide-react. Match the powerlifting app's dependency versions.

Add to `dependencies`:
```json
"@mantine/core": "^9.0.1",
"@mantine/hooks": "^9.0.1",
"@mantine/notifications": "^9.0.1",
"lucide-react": "^0.300.0",
"react": "^19.2.5",
"react-dom": "^19.2.5"
```

Add to `devDependencies`:
```json
"@types/react": "^19.0.0",
"@types/react-dom": "^19.0.0",
"postcss-preset-mantine": "^1.18.0",
"postcss-simple-vars": "^7.0.1"
```

After editing, run:
```bash
cd utils/main-portal/frontend && npm install
```

---

## Step 2 — `postcss.config.js`

File: `utils/main-portal/frontend/postcss.config.js`

Replace entirely:
```js
export default {
  plugins: {
    'postcss-preset-mantine': {},
    'postcss-simple-vars': {
      variables: {
        'mantine-breakpoint-xs': '36em',
      },
    },
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

---

## Step 3 — `src/index.css`

File: `utils/main-portal/frontend/src/index.css`

Replace the entire file. Exact same approach as the directives portal migration (Step 2 of that plan):
copy `utils/powerlifting-app/frontend/src/index.css` as the base, then:

1. Remove all powerlifting-specific component CSS classes (`if-session-*`, `if-exercise-*`,
   `if-calendar-*`, `if-dashboard-*`, `if-designer-*`, `if-supp-*`, `if-lift-*`, `if-video-*`, `rbc-*`)
2. Keep the full token set in `:root` and `.dark` (all `--bg-*`, `--border-*`, `--accent-*`, `--status-*`,
   `--font-*`, `--border-radius-*`, `--color-*` aliases)
3. Keep the `@layer base` block with `background: var(--bg-base)` on `body` — critical
4. Keep the Mantine override block (`:root, [data-mantine-color-scheme]`)
5. Keep `.if-card`, `.if-list-row`, `.if-pill-*`, `.if-small-label`, `.if-page-header`, `.if-page-title`
6. Keep `::-webkit-scrollbar` block
7. The main portal uses `--accent-blue` (not violet) — keep that naming as-is from the powerlifting base

---

## Step 4 — `src/main.tsx`

File: `utils/main-portal/frontend/src/main.tsx`

Replace entirely. Wrap the app in `MantineProvider` with the same theme and resolver as the
powerlifting app. Use `primaryColor: 'blue'` (hub is a neutral dashboard, not branded violet).

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MantineProvider, createTheme, type CSSVariablesResolver } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import App from './App'
import './index.css'

const theme = createTheme({
  primaryColor: 'blue',
  defaultRadius: 'sm',
  fontFamily: "'DM Sans', sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', monospace",
  headings: {
    fontFamily: "'Barlow Condensed', sans-serif",
    fontWeight: '600',
  },
})

const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--accent-blue': '#3b82f6',
  },
  light: {
    '--bg-base': '#f6f8fb',
    '--bg-surface': '#ffffff',
    '--bg-elevated': '#f1f5f9',
    '--bg-hover': '#eaf2ff',
    '--border-subtle': '#e2e8f0',
    '--border-default': '#cbd5e1',
    '--accent-blue-dim': '#dbeafe',
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
    '--accent-blue-dim': '#1e3a5f',
    '--text-primary': '#e2e6f0',
    '--text-secondary': '#8891aa',
    '--text-muted': '#4a5068',
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      cssVariablesResolver={cssVariablesResolver}
    >
      <Notifications position="top-right" />
      <BrowserRouter basename="/">
        <App />
      </BrowserRouter>
    </MantineProvider>
  </React.StrictMode>
)
```

---

## Step 5 — `src/App.tsx`

File: `utils/main-portal/frontend/src/App.tsx`

Remove the manual dark mode state, toggle button, and `document.documentElement.classList` calls.
`MantineProvider defaultColorScheme="auto"` handles this entirely. Replace the raw layout div with
a Mantine `AppShell`.

```tsx
import { Routes, Route } from 'react-router-dom'
import { AppShell, Group, Text } from '@mantine/core'
import { Hub } from './pages/Hub'

export default function App() {
  return (
    <AppShell header={{ height: 52 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Text fw={600} size="lg" ff="var(--font-sans)" c="var(--text-primary)">
            IF Hub
          </Text>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Hub />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  )
}
```

Note: `AppShell.Header` background and border will pick up `--mantine-color-body` and
`--mantine-color-default-border` from the Mantine overrides in `index.css`. No manual styling needed.

---

## Step 6 — `src/pages/Hub.tsx`

File: `utils/main-portal/frontend/src/pages/Hub.tsx`

Replace all Tailwind layout classes with Mantine layout components.
Logic and data wrangling (store, formatters, conditional lines) stays exactly the same.

Layout replacement map:

| Tailwind | Mantine |
|---|---|
| `<div className="space-y-6">` | `<Stack gap="xl">` |
| `<h2 className="text-sm font-medium text-muted-foreground mb-2">` | `<Text size="sm" fw={500} c="var(--text-secondary)" mb={8}>` |
| `<div className="grid grid-cols-1 md:grid-cols-2 gap-4">` | `<SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">` |
| `<div className="p-4 rounded-lg bg-destructive/10 border border-destructive text-destructive">` | `<Box p="sm" style={{ background: 'var(--status-danger-bg)', border: '0.5px solid var(--status-danger-border)', borderRadius: 'var(--border-radius-lg)' }}>` |
| `<p className="font-medium">` | `<Text fw={500}>` |
| `<p className="text-sm mt-1">` | `<Text size="sm" mt={4}>` |
| `<p className="text-xs text-muted-foreground text-right">` | `<Text size="xs" c="var(--text-muted)" ta="right">` |

Required Mantine imports to add:
```tsx
import { Stack, SimpleGrid, Text, Box } from '@mantine/core'
```

---

## Step 7 — `src/components/PortalCard.tsx`

File: `utils/main-portal/frontend/src/components/PortalCard.tsx`

Replace the raw `<div>` structure with a Mantine `Paper` using the `if-card` CSS pattern.
Status dot and badge use inline styles with CSS var tokens.

```tsx
import { Paper, Group, Text, Box, Anchor } from '@mantine/core'

interface PortalCardProps {
  name: string
  icon: string
  href: string
  status: 'reachable' | 'unreachable'
  pendingCount?: number
  lines: string[]
}

export function PortalCard({ name, icon, href, status, pendingCount, lines }: PortalCardProps) {
  const isReachable = status === 'reachable'

  const card = (
    <Paper
      p="md"
      style={{
        background: 'var(--bg-surface)',
        border: '0.5px solid var(--border-subtle)',
        borderRadius: 'var(--border-radius-lg)',
        transition: 'background 120ms ease, border-color 120ms ease',
        cursor: isReachable ? 'pointer' : 'default',
        opacity: isReachable ? 1 : 0.6,
      }}
    >
      <Group justify="space-between" mb={8}>
        <Group gap={8}>
          <Text size="xl">{icon}</Text>
          <Text fw={500} c="var(--text-primary)">{name}</Text>
          {pendingCount !== undefined && pendingCount > 0 && (
            <Box
              style={{
                background: 'var(--status-danger-bg)',
                border: '0.5px solid var(--status-danger-border)',
                borderRadius: 999,
                color: 'var(--status-danger-text)',
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 1,
                padding: '2px 8px',
              }}
            >
              {pendingCount}
            </Box>
          )}
        </Group>
        <Box
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            flexShrink: 0,
            background: isReachable ? 'var(--status-success-text)' : 'var(--text-muted)',
          }}
        />
      </Group>
      {lines.map((line, i) => (
        <Text key={i} size="sm" c="var(--text-secondary)">{line}</Text>
      ))}
    </Paper>
  )

  if (!isReachable) return card

  return (
    <Anchor href={href} target="_blank" rel="noopener noreferrer" underline="never">
      {card}
    </Anchor>
  )
}
```

---

## Step 8 — `src/components/SnapshotBar.tsx`

File: `utils/main-portal/frontend/src/components/SnapshotBar.tsx`

Replace raw divs and Tailwind classes with Mantine `Group` and `Text`.
Replace `text-green-600 dark:text-green-400` with CSS var token expressions.

```tsx
import { Group, Text, Box } from '@mantine/core'
import type { FinanceData, HealthData } from '../types'
import { formatCurrency, formatDaysUntil } from '../utils/formatters'

interface SnapshotBarProps {
  finance: FinanceData | null
  health: HealthData | null
  loading?: boolean
}

export function SnapshotBar({ finance, health, loading }: SnapshotBarProps) {
  if (loading) {
    return (
      <Box
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 24,
          padding: '10px 16px',
          borderBottom: '0.5px solid var(--border-subtle)',
        }}
      >
        {[32, 28, 24].map(w => (
          <Box key={w} style={{ height: 16, width: w * 4, background: 'var(--bg-elevated)', borderRadius: 4 }} />
        ))}
      </Box>
    )
  }

  const items: { label: string; value: string; positive?: boolean | null }[] = []

  if (finance) {
    items.push({ label: 'Net Worth', value: formatCurrency(finance.net_worth), positive: finance.net_worth >= 0 })
    items.push({ label: 'Surplus', value: formatCurrency(finance.monthly_surplus) + '/mo', positive: finance.monthly_surplus >= 0 })
  }
  if (health) {
    items.push({ label: 'Week', value: health.current_week, positive: null })
    if (health.days_to_comp !== null) {
      items.push({ label: 'Comp', value: formatDaysUntil(health.days_to_comp), positive: health.days_to_comp > 14 ? null : false })
    }
  }

  if (items.length === 0) return null

  return (
    <Box style={{ display: 'flex', flexWrap: 'wrap', gap: 24, padding: '10px 16px', borderBottom: '0.5px solid var(--border-subtle)' }}>
      {items.map((item, i) => (
        <Group key={i} gap={6}>
          <Text size="sm" c="var(--text-secondary)">{item.label}:</Text>
          <Text
            size="sm"
            fw={500}
            c={
              item.positive === null ? 'var(--text-primary)' :
              item.positive ? 'var(--status-success-text)' :
              'var(--status-danger-text)'
            }
          >
            {item.value}
          </Text>
        </Group>
      ))}
    </Box>
  )
}
```

---

## Step 9 — `src/components/AlertsList.tsx`

File: `utils/main-portal/frontend/src/components/AlertsList.tsx`

Replace all raw divs and hardcoded dark-variant Tailwind colors with CSS var tokens.

```tsx
import { Stack, Text, Box } from '@mantine/core'

interface AlertsListProps {
  alerts: string[]
  loading?: boolean
}

export function AlertsList({ alerts, loading }: AlertsListProps) {
  if (loading) {
    return (
      <Stack gap={8}>
        {[100, 75].map(w => (
          <Box key={w} style={{ height: 40, width: `${w}%`, background: 'var(--bg-elevated)', borderRadius: 'var(--border-radius-md)' }} />
        ))}
      </Stack>
    )
  }

  if (alerts.length === 0) {
    return (
      <Box p="sm" style={{ background: 'var(--status-success-bg)', border: '0.5px solid var(--status-success-border)', borderRadius: 'var(--border-radius-lg)' }}>
        <Text size="sm" c="var(--status-success-text)">No alerts — everything looks good</Text>
      </Box>
    )
  }

  return (
    <Stack gap={6}>
      <Text size="sm" fw={500} c="var(--text-secondary)">
        ⚠️ Alerts
      </Text>
      {alerts.map((alert, i) => (
        <Box
          key={i}
          p="xs"
          style={{
            background: 'var(--status-warning-bg)',
            border: '0.5px solid var(--status-warning-border)',
            borderRadius: 'var(--border-radius-md)',
          }}
        >
          <Text size="sm" c="var(--status-warning-text)">{alert}</Text>
        </Box>
      ))}
    </Stack>
  )
}
```

---

## Step 10 — `src/components/SignalStrip.tsx`

File: `utils/main-portal/frontend/src/components/SignalStrip.tsx`

Replace raw divs and Tailwind color class strings with Mantine `Group`, `Text`, `Badge`, and CSS var tokens.
The `getScoreColor`, `getTrendColor`, `getLifeLoadColor` functions in `formatters.ts` currently return
Tailwind class strings — after Step 11 they will return CSS var values instead.

```tsx
import { Group, Text, Badge, Box } from '@mantine/core'
import type { SignalsData } from '../types'
import { getScoreColor, getTrendColor, getLifeLoadColor, getTrendIcon } from '../utils/formatters'

interface SignalStripProps {
  signals: SignalsData | null
  loading?: boolean
}

export function SignalStrip({ signals, loading }: SignalStripProps) {
  const containerStyle = {
    display: 'flex', flexWrap: 'wrap' as const, alignItems: 'center', gap: 24,
    padding: '10px 16px',
    background: 'var(--bg-elevated)',
    borderRadius: 'var(--border-radius-lg)',
  }

  if (loading) {
    return (
      <Box style={containerStyle}>
        {[80, 64, 80, 64].map((w, i) => (
          <Box key={i} style={{ height: 20, width: w, background: 'var(--bg-surface)', borderRadius: 4 }} />
        ))}
      </Box>
    )
  }

  if (!signals) {
    return (
      <Box style={containerStyle}>
        <Text size="sm" c="var(--text-secondary)">Signal data unavailable</Text>
      </Box>
    )
  }

  return (
    <Box style={containerStyle}>
      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Score:</Text>
        <Text size="lg" fw={600} style={{ color: getScoreColor(signals.mental_health_score) }}>
          {signals.mental_health_score.toFixed(1)}
        </Text>
      </Group>

      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Trend:</Text>
        <Text fw={500} style={{ color: getTrendColor(signals.trend) }}>
          {getTrendIcon(signals.trend)} {signals.trend.replace('_', ' ')}
        </Text>
      </Group>

      <Group gap={6}>
        <Text size="sm" c="var(--text-secondary)">Life Load:</Text>
        <Badge
          size="sm"
          variant="light"
          style={{
            background: getLifeLoadColor(signals.life_load).bg,
            color: getLifeLoadColor(signals.life_load).text,
            border: `0.5px solid ${getLifeLoadColor(signals.life_load).border}`,
            textTransform: 'capitalize',
          }}
        >
          {signals.life_load.replace('_', ' ')}
        </Badge>
      </Group>

      {signals.social_battery && (
        <Group gap={6}>
          <Text size="sm" c="var(--text-secondary)">Social:</Text>
          <Text size="sm" fw={500} c="var(--text-primary)" style={{ textTransform: 'capitalize' }}>
            {signals.social_battery}
          </Text>
        </Group>
      )}
    </Box>
  )
}
```

---

## Step 11 — `src/utils/formatters.ts`

File: `utils/main-portal/frontend/src/utils/formatters.ts`

The color helper functions currently return Tailwind class strings. `SignalStrip` after Step 10
expects them to return CSS var values (plain color strings for `color:` and an object for `getLifeLoadColor`).

Update the three color helpers:

```ts
// getScoreColor: returns a CSS color string
export function getScoreColor(score: number): string {
  if (score >= 7) return 'var(--status-success-text)'
  if (score >= 4) return 'var(--status-warning-text)'
  return 'var(--status-danger-text)'
}

// getTrendColor: returns a CSS color string
export function getTrendColor(trend: string): string {
  if (trend === 'improving') return 'var(--status-success-text)'
  if (trend === 'declining') return 'var(--status-danger-text)'
  return 'var(--text-secondary)'
}

// getLifeLoadColor: returns an object with bg, text, border CSS var strings
export function getLifeLoadColor(load: string): { bg: string; text: string; border: string } {
  if (load === 'low') return { bg: 'var(--status-success-bg)', text: 'var(--status-success-text)', border: 'var(--status-success-border)' }
  if (load === 'high' || load === 'very_high') return { bg: 'var(--status-danger-bg)', text: 'var(--status-danger-text)', border: 'var(--status-danger-border)' }
  return { bg: 'var(--status-neutral-bg)', text: 'var(--status-neutral-text)', border: 'var(--status-neutral-border)' }
}
```

All other formatters (`formatCurrency`, `formatDaysUntil`, `formatRelativeTime`, `getTrendIcon`)
are pure value formatters and do not change.

---

## Step 12 — `index.html`

File: `utils/main-portal/frontend/index.html`

Add the CSP meta tag matching the gateway `security-only` snippet.
The main portal does not show Discord avatars so `cdn.discordapp.com` is not needed here.

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' https://cloudflareinsights.com; frame-ancestors 'self';" />
    <title>IF Hub</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## Step 13 — Verify no Tailwind classes remain in component JSX

After all steps, run:
```bash
grep -rn 'className=' utils/main-portal/frontend/src/
```

Must return zero hits. Every `className` in component/page JSX must be replaced with
a Mantine prop or `style` prop.

---

## Step 14 — Build verification

```bash
cd utils/main-portal/frontend
npm run build
```

Must pass with zero errors. CSS bundle should be ~520KB+ (Mantine bundled locally).

```bash
grep -i 'googleapis' utils/main-portal/frontend/dist/index.html
# must return nothing
```

---

## Files changed summary

| File | Change |
|---|---|
| `frontend/package.json` | Add `@mantine/core`, `@mantine/hooks`, `@mantine/notifications`, `lucide-react`, bump React to 19, add `postcss-preset-mantine`, `postcss-simple-vars` |
| `frontend/postcss.config.js` | Add `postcss-preset-mantine` + `postcss-simple-vars` |
| `frontend/src/index.css` | Full rewrite — copy powerlifting base, strip powerlifting-specific classes |
| `frontend/src/main.tsx` | Add `MantineProvider`, `createTheme`, `cssVariablesResolver`, `Notifications` |
| `frontend/src/App.tsx` | Remove manual dark mode state/toggle, replace raw layout with Mantine `AppShell` |
| `frontend/src/pages/Hub.tsx` | Replace all Tailwind layout classes with Mantine `Stack`, `SimpleGrid`, `Text`, `Box` |
| `frontend/src/components/PortalCard.tsx` | Replace raw div + Tailwind with Mantine `Paper`, `Group`, `Text`, `Box`, `Anchor` |
| `frontend/src/components/SnapshotBar.tsx` | Replace Tailwind color classes with CSS var tokens, raw div with Mantine `Group`/`Box` |
| `frontend/src/components/AlertsList.tsx` | Replace hardcoded dark-variant Tailwind colors with CSS var tokens |
| `frontend/src/components/SignalStrip.tsx` | Replace raw div + Tailwind with Mantine `Box`/`Group`/`Text`/`Badge` + CSS vars |
| `frontend/src/utils/formatters.ts` | Change color helpers to return CSS var strings instead of Tailwind class names |
| `frontend/index.html` | Add CSP meta tag |

**Files NOT changed:**
- `frontend/src/store/hubStore.ts` (logic only, no UI)
- `frontend/src/types/index.ts` (types only)
- `frontend/tailwind.config.ts` (still needed for `@tailwind` directives in `index.css`)
- All backend files
