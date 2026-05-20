# Powerlifting App Design Spec

Last reviewed: 2026-05-20

This document describes the current Powerlifting App UI and interaction model for a redesign workflow, especially one driven by an AI connected to Figma. It should be treated as a current-state product and design handoff, not as a new visual direction. The redesign can improve hierarchy and polish, but it should preserve the app logic, information density, page inventory, and major state permutations described here.

## Product Intent

The app is a single-athlete powerlifting training portal. It is a dense operational tool for tracking training, planning blocks, analyzing readiness, importing templates, evaluating programs, and reviewing competition prep.

Design goals:

- Prioritize fast scanning, repeated use, and data entry over marketing-style presentation.
- Keep information dense but organized: compact panels, tables, charts, badges, and controlled forms are preferred.
- Make training state obvious: planned vs completed, active vs archived, read-only vs writable, cache hit vs generating, current week vs full block.
- Preserve mobile usability for in-gym logging. Session detail and compact sessions must remain comfortable on a phone.
- Use icons where they clarify actions, especially tools, settings, upload, save, refresh, delete, AI actions, and navigation.
- Avoid decorative hero layouts, oversized cards, gradient-heavy visual language, and purely illustrative content.

Primary user:

- A powerlifter who plans and logs training, reviews analysis, tracks bodyweight/biometrics, and may use AI-assisted notes, auto-regulation, and program evaluation.

Secondary design consumer:

- A Figma-connected AI that needs enough structure to recreate page frames, responsive variants, reusable components, and interaction states.

## Current Technology And Design System

Frontend:

- React 19 with React Router.
- Mantine 9 for layout, forms, modals, drawers, tabs, tables, notifications, dates, and theme primitives.
- Tailwind CSS for CSS variable color tokens and utility classes.
- lucide-react for icons.
- Recharts for charts.
- dnd-kit for drag and drop in session/program editing.

Global component style:

- Default Mantine radius is `md`.
- CSS radius token is `--radius: 0.5rem`, equal to 8px.
- Most surfaces are `Paper` or `Card` with `withBorder`, padding `md` or `lg`, and radius `md`.
- Buttons use Mantine variants: `filled` for primary actions, `light` for secondary emphasis, `default` for neutral/cancel, `subtle` for toolbar actions, `red` for destructive actions.
- Tables use compact text, right-aligned numeric cells, and horizontal overflow wrappers when columns can exceed mobile width.
- Badges communicate status and data quality. Use `variant="light"` for status metadata and `variant="filled"` for compact load-source badges.

## Color And Visual Tokens

The app supports light, dark, and system theme modes. Theme is controlled in the Settings drawer and applied by toggling `.dark` and `data-mantine-color-scheme`.

Light CSS tokens:

| Token | HSL |
| --- | --- |
| background | `0 0% 100%` |
| foreground | `222.2 84% 4.9%` |
| card | `0 0% 100%` |
| card-foreground | `222.2 84% 4.9%` |
| primary | `221.2 83.2% 53.3%` |
| primary-foreground | `210 40% 98%` |
| secondary | `210 40% 96.1%` |
| secondary-foreground | `222.2 47.4% 11.2%` |
| muted | `210 40% 96.1%` |
| muted-foreground | `215.4 16.3% 46.9%` |
| accent | `210 40% 96.1%` |
| accent-foreground | `222.2 47.4% 11.2%` |
| destructive | `0 84.2% 60.2%` |
| destructive-foreground | `210 40% 98%` |
| border/input | `214.3 31.8% 91.4%` |
| ring | `221.2 83.2% 53.3%` |

Dark CSS tokens:

| Token | HSL |
| --- | --- |
| background | `222.2 84% 4.9%` |
| foreground | `210 40% 98%` |
| card | `222.2 84% 4.9%` |
| card-foreground | `210 40% 98%` |
| primary | `217.2 91.2% 59.8%` |
| primary-foreground | `222.2 47.4% 11.2%` |
| secondary | `217.2 32.6% 17.5%` |
| secondary-foreground | `210 40% 98%` |
| muted | `217.2 32.6% 17.5%` |
| muted-foreground | `215 20.2% 65.1%` |
| accent | `217.2 32.6% 17.5%` |
| accent-foreground | `210 40% 98%` |
| destructive | `0 62.8% 30.6%` |
| destructive-foreground | `210 40% 98%` |
| border/input | `217.2 32.6% 17.5%` |
| ring | `224.3 76.3% 48%` |

Semantic color usage:

- Blue: primary navigation, active controls, links, cached AI data, informational alerts, load target of type RPE, selected nav.
- Green: success, completed sessions/sets, productive zones, good alignment, ready/readiness, just-generated AI content.
- Yellow: caution, skipped sets, draft templates, missing data gates, warnings, mixed alignment.
- Orange: high fatigue, regeneration/refresh emphasis, denied or caution AI states.
- Red: destructive actions, failed sets, errors, recovery/critical states, invalid input, unresolvable load badges.
- Gray: archived, inactive, pending, unknown, no data, disabled, read-only context.
- Violet: strong correlation strength in AI analysis.
- Phase colors: generated by `phaseColor(...)` and used as colored dots, left borders, and phase badges. Redesign should preserve phase color as a fast visual signal.

Figma guidance:

- Build semantic color styles named by purpose, not only by hue: `Status/Success`, `Status/Caution`, `Status/Error`, `Status/Info`, `Status/Neutral`, `AI/Cached`, `AI/Generated`.
- Keep light and dark mode variants for all main surfaces, badges, form fields, charts, and tables.
- Use borders and spacing to separate dense information. Avoid relying only on colored backgrounds.

## Typography, Spacing, And Iconography

Typography:

- Page titles usually use Mantine `Title order={2}`.
- Section titles use `Title order={3}` or `Text fw={500/600}`.
- Body copy uses `Text size="sm"`; helper text uses `Text size="xs" c="dimmed"`.
- Metric cards often use `Text fz="xl"` or `lg` with `fw={700}` for the number, with an `xs` dimmed label.
- Avoid giant display type inside app pages.

Spacing:

- Page stacks generally use `Stack gap="lg"` or `md`.
- Repeated cards use `SimpleGrid` with `spacing="md"`.
- Compact controls use `Group gap="xs"`.
- Forms usually group fields in `SimpleGrid cols={{ base: 1, sm: 2/3/4 }}` depending on density.

Iconography:

- Icons are lucide-react.
- Common icons:
  - Dashboard: `LayoutDashboard`
  - Sessions: `Calendar`
  - Designer: `ClipboardList`
  - Analysis: `Activity`
  - Tools: `Wrench`
  - Save: `Save`
  - Delete: `Trash2`
  - Upload/video: `Upload`, `Film`
  - Settings: `Settings`
  - AI: `Bot`, `Brain`, `Wand2`, `Sparkles`
  - Refresh/regenerate: `RefreshCw`
  - Back/close: `ArrowLeft`, `X`
- Icon buttons should include tooltips or accessible labels when the visual meaning is not obvious.

## App Shell And Navigation

All routes currently render inside `AppShell`, including `/login` and `/auth/callback`.

Desktop shell:

- Fixed header height: 60px.
- Desktop navbar width: 256px.
- Navbar breakpoint: Mantine `md`.
- Header contains the top bar.
- Desktop navbar contains a vertical scrollable nav list with all navigation items.
- Main content uses Mantine `AppShell.Main` with padding `md`.
- Read-only banner appears at the top of main content when `readOnly` is true.
- Settings drawer is mounted globally.

Mobile shell:

- Sidebar collapses on mobile.
- A fixed bottom navigation appears below `md`.
- Mobile footer height is `calc(60px + env(safe-area-inset-bottom, 0px))`.
- Main bottom padding is large enough to clear the bottom nav and browser chrome:
  - base: `calc(180px + env(safe-area-inset-bottom, 0px) + var(--app-browser-bottom-overlap, 0px))`
  - md and up: `140px`
- The app updates CSS variables from `window.visualViewport`:
  - `--app-viewport-height`
  - `--app-browser-bottom-overlap`
- Mobile input fields use a 16px font-size plus transform scale to avoid iOS auto-zoom while preserving small visual density.

Desktop navigation items:

- Dashboard: `/`
- Sessions: `/sessions`
- Designer: `/designer`
- Charts: `/charts`
- Analysis: `/analysis`
- Rankings: `/rankings`
- Tools: `/tools`
- Supplements: `/supplements`
- Biometrics: `/biometrics`
- Maxes: `/maxes`
- Videos: `/videos`
- Profiles: `/profiles`
- About: `/about`

Current nav caveat:

- `/charts` appears in the desktop primary nav but is not defined in `App.tsx`. A redesign should either map Charts to the Analysis chart view, remove it, or add an explicit Charts page.

Mobile primary nav:

- Dashboard: `/`
- Designer: `/designer`
- Sessions: `/sessions`
- Analysis: `/analysis`
- More menu for remaining pages.
- Mobile nav icons use filled blue when active and subtle gray when inactive.

Top bar:

- Left side: program version selector menu.
- Right side: unit toggle (`KG` or `LB`) and Settings button.
- Version menu shows current visible versions, checkmark on selected version, and actions:
  - Fork this version
  - Archive or unarchive version
  - Convert to Template
- Archived version state changes the selector color to gray and shows an `Archived` badge.
- Read-only users cannot fork, archive, unarchive, or convert to template.

Settings drawer:

- Right-side drawer, size `sm`, title `Settings`.
- Sections:
  - Account: loading state, signed-in profile, sign out, or sign in with Discord.
  - Public profile: visibility segmented control, display name, bio, public training summary switch, save profile button.
  - Appearance: Light, Dark, System buttons with icons.
  - Default Sessions View: Agenda, Month, Compact select.
  - Sex: Male/Female segmented control, used for DOTS and synchronized to program metadata when writable.
  - Training Week Start: select from week start days.
  - Bar Weight: numeric input in active unit, used for plate calculator.

Read-only banner:

- Yellow light alert with Eye icon.
- Text: read-only mode.
- Sign in button with LogIn icon.
- It appears for public/demo/operator data and all unauthenticated fallback views.

## Route And Page Inventory

| Route | Page | Purpose | Key design frame |
| --- | --- | --- | --- |
| `/login` | Login | Discord sign-in entry and auth errors | Centered login card |
| `/auth/callback` | AuthCallback | OAuth verification loader | Centered loader |
| `/` | Dashboard | Block overview, metrics, maxes, phases, lift profiles, AI profile helpers | Dense dashboard |
| `/lift-profiles/:lift` | Lift Profile | Per-lift profile detail and editing | Detail/editor page |
| `/calendar` | Redirect | Redirects to `/sessions` | No frame needed |
| `/sessions` | CalendarPage | Month, Agenda, or Compact session browser | Sessions hub |
| `/list` | Redirect | Redirects to `/sessions?view=Compact` | No frame needed |
| `/session/:date/:index?` | SessionDetailPage | Full-page session logging/editing | Mobile-first session detail |
| `/list/:date/:index?` | SessionDetailPage | Session detail with compact-list back route | Same as session detail |
| `/designer` | DesignerLanding | Program designer section landing | Card grid |
| `/designer/phases` | DesignerPhases | Phase list, block filter, add/edit/delete phases | Phase manager |
| `/designer/sessions` | DesignerPage | Session planning by week with drag/drop exercises | Program session planner |
| `/designer/goals` | GoalsPage | Block goals, competition targets, qualifying goals | Goal accordions/forms |
| `/designer/federations` | FederationsPage | Federation and qualifying-standard library | Data manager |
| `/designer/competitions` | CompetitionsPage | Competition planning and results | Competition form/list |
| `/designer/glossary` | GlossaryPage | Exercise library, categories, video links | Exercise glossary table/forms |
| `/designer/import` | ImportWizardPage | Multi-step spreadsheet/program import | Stepper wizard |
| `/designer/templates` | TemplateLibraryPage | Template tabs and card grid | Template library |
| `/designer/templates/new` | TemplateCreatePage | Create blank template | Narrow form |
| `/designer/templates/import` | TemplateImportPage | Upload template spreadsheet and poll job | Dropzone and job status |
| `/designer/template` | TemplateDetailPage | Query-param legacy template detail | Template detail |
| `/designer/template/edit` | TemplateEditPage | Query-param legacy template edit | Template editor |
| `/designer/templates/:sk` | TemplateDetailPage | Template detail, AI evaluation, apply flow | Template detail with side panel |
| `/designer/templates/:sk/edit` | TemplateEditPage | Template metadata, phases, sessions editing | Template editor |
| `/analysis` | AnalysisPage | Weekly, past block, lifetime compare analytics | Analytics workstation |
| `/rankings` | RankingsPage | OpenPowerlifting rankings filters and results | Filter/results split |
| `/notes` | NotesPage | Dated training notes | Notes feed/editor |
| `/supplements` | SupplementsPage | Supplement phases and peak-week protocols | Accordion editor |
| `/biometrics` | BiometricsPage | Nutrition, sleep, water, consistency, notes | Biometric entry feed |
| `/diet` | BiometricsPage | Alias for biometrics | Same as biometrics |
| `/maxes` | MaxesPage | All-time maxes and progress charts | Table plus charts |
| `/tools` | ToolsPage | Tool launcher grid | Tool cards |
| `/tools/plate` | PlateCalculator | Plate loading calculator | Calculator form/result |
| `/tools/dots` | DotsCalculator | DOTS calculator | Calculator form/result |
| `/tools/weight` | WeightTracker | Bodyweight tracker | Log and chart |
| `/tools/percent` | PercentTable | Percent of max table | Table generator |
| `/tools/converter` | UnitConverter | kg/lb conversion | Simple converter |
| `/tools/attempts` | AttemptSelector | Competition attempt planning | Attempt planning tool |
| `/videos` | VideosPage | Video library, filters, player modal | Video feed |
| `/profiles` | ProfilesPage | Public profile search | Search plus profile grid |
| `/about` | AboutPage | Methodology and formula documentation | Long-form reference |

Unrouted files currently exist for `TimelinePage` and `DietNotesPage`. They are not active in `App.tsx` and should not be primary redesign frames unless the route map changes.

## Cross-App State Model

Authentication states:

- Loading auth: app waits for `/api/auth/me`.
- Unauthenticated or auth error: user is treated as public operator dataset with `mapped_pk="operator"` and `readOnly=true`.
- Authenticated writable user: `readOnly=false`, private mapped profile key from the backend.
- Logout: POST `/api/auth/logout`, then local user becomes null and app returns to read-only operator dataset.

Program states:

- Program loading: centered loader or dimmed "Loading..." text depending on page.
- Program missing or setup required: `SetupOnboarding` appears on Dashboard/Sessions.
- Current program loaded: all normal views render.
- Archived program: top bar shows Archived badge; destructive/write actions should be disabled or treated cautiously.
- Multiple versions: top bar selector lists active versions plus selected archived version.

Permission states:

- Read-only mode disables write actions, save buttons, import/apply actions, AI generation actions that mutate/cache, archive/fork/template conversion, upload, delete, and profile updates.
- Read-only mode still allows viewing public/demo data, browsing pages, changing local unit/theme/default view, and using some local calculators.

Feedback states:

- Toast notifications use Mantine Notifications at top-right.
- Toast colors: green success, yellow warning, red error.
- Loading buttons should use built-in `loading` spinners.
- Long-running uploads/imports/AI generation should expose progress, polling badges, or loading overlays.
- Empty states should be centered or card-based with dimmed text and a direct next action.

## Primary Flows

### Sign In, Read-Only, And First Setup

Current auth flow:

1. App mounts and calls `/api/auth/me`.
2. If it succeeds with a user, the app stores user, mapped profile key, and read-only flag.
3. If it fails or returns no writable user, the app falls back to public operator data in read-only mode.
4. Clicking "Sign in with Discord" navigates to `/api/auth/discord/login`.
5. Backend handles Discord OAuth and redirects to `/auth/callback`.
6. Callback page shows a centered loader and text "Signing you in...".
7. Callback verifies `/api/auth/me`; success navigates to `/`, failure navigates to `/login?error=auth_failed`.

Login page:

- Centered card, width about 400px.
- Brand text: `NoLift Training`.
- Primary button: `Sign in with Discord`.
- Helper copy says personal data requires sign-in and shared demo data is visible without sign-in.
- Error messages:
  - `no_code`: Discord authorization code was not received.
  - `invalid_state`: security verification failed.
  - `auth_failed`: Discord authentication failed.

First setup:

- If read-only or no user, setup panel asks user to sign in to create a private training block.
- Signed-in users can create a first block from:
  - Blank block.
  - Manual session design.
  - Template.
- Setup fields:
  - Block name.
  - Start date.
  - Week starts.
  - Template select when templates are available.
  - Missing maxes when template application is blocked.
- Successful setup routes:
  - Blank block -> Dashboard.
  - Manual sessions -> Designer Sessions.
  - Template -> Sessions.
- Template gate:
  - If backend returns `gate_blocked`, show yellow missing-max alert.
  - Render one numeric e1RM input per missing lift/exercise.
  - Retry setup with entered maxes.

### Program Version Flow

Version selector:

- User opens the top-left version menu.
- Current version is checked.
- Current selected archived version remains visible even if archived versions are otherwise hidden.
- Selecting a version loads that program version.

Actions:

- Fork this version:
  - Disabled in read-only.
  - Shows loading text while forking.
  - Success toast: "Version forked".
  - Failure toast: "Fork failed".
- Archive/unarchive:
  - Disabled in read-only.
  - Uses red archive action for active version, blue restore action for archived version.
  - Success toast: "Version archived" or "Version unarchived".
- Convert to Template:
  - Disabled in read-only.
  - Uses browser prompt for template name.
  - Success toast: "Template created".

### Sessions Flow

Sessions page modes:

- Month: calendar-like date browser with phase-color dots on session days. Clicking a session day opens detail.
- Agenda: week-grouped session rows, automatically scrolls to the closest session to today on first render.
- Compact: mobile-friendly Sessions by Week list with expandable weeks and sticky top filter.

Shared sessions behavior:

- `view` query param controls Month, Agenda, or Compact.
- `block` query param filters sessions when multiple blocks exist.
- Default sessions view comes from Settings.
- `/calendar` redirects to `/sessions`.
- `/list` redirects to `/sessions?view=Compact`.

Month view:

- Shows a calendar with session dates marked by colored dots.
- Completed sessions render at full color; incomplete sessions use lower opacity.
- Disabled days without sessions are not clickable.

Agenda view:

- Rows are unstyled buttons containing bordered `Paper`.
- Each row uses a 4px left border in the phase color.
- Contains date, phase badge, preview exercise names, and completed status icon.
- Compact row variant truncates exercise previews.

Compact view:

- Sticky header with page title, block select, and Add Session button.
- Mobile uses a floating circular Add Session action button above the bottom nav.
- Weeks expand/collapse.
- The current/closest week auto-expands and scrolls into view on first render.
- Add Session modal asks for date, creates empty session, then opens session detail.

Session detail:

- `/session/:date/:index?` resolves the session by date and optional array index.
- Loading state uses centered loader.
- Missing date shows red alert and Back button.
- Missing session shows yellow alert and Back button.
- Actual editor is `SessionDrawer` in `mode="page"` with max width around 1040px.

Session editor layout:

- Header:
  - Back or close icon.
  - Session date/date picker.
  - Phase/status metadata.
  - Save state text: "Saving...", "Unsaved changes", "Saved", or "No changes".
  - Reset/discard, Save, Complete/Reopen, Delete actions.
- Wellness:
  - Segmented control: record or skip.
  - When recorded, five sliders from 1 to 5: Sleep, Soreness, Mood, Stress, Energy.
  - Skipping removes wellness from the session.
- Exercises:
  - One bordered row/card per exercise.
  - Drag handle on left for ordering.
  - Autocomplete exercise name from glossary.
  - Inputs: sets, reps, weight in current unit, RPE, notes.
  - RPE validation allows 1 to 10 with whole or .5 increments.
  - Set status controls render one compact control per set.
  - Set statuses: pending, completed, failed, skipped.
  - Failed set selection opens a failure-reason modal.
  - Failed reasons include strength failure, technical failure, command failure, grip, depth, pause, lockout, balance, pain, fatigue, and misload/bad attempt selection.
- Exercise actions:
  - Desktop shows action buttons.
  - Mobile uses a compact menu/action icon pattern.
  - Delete is red.
  - Bot opens auto-regulation.
  - Calculator opens session toolkit.
- Videos:
  - Video upload button opens upload modal.
  - Existing videos render in a grid.
  - Upload modal requires file and exercise name; set number and notes are optional.
  - Upload progress uses animated progress bar and percent text.
- Notes:
  - Session notes textarea.
  - "Help write session notes" opens AI notes helper.

Session save behavior:

- Local edits set `hasChanges`.
- Auto-save starts after 1500ms when writable.
- Manual save validates RPE before saving.
- Closing with unsaved changes opens discard confirmation.
- Browser unload is guarded while saving or dirty.
- Failed auto-save keeps dirty state and shows error toast.

### Session AI Flows

Auto-regulation:

- Entry point: Bot button on an exercise.
- Modal title: Auto-regulation.
- Shows target exercise name, sets/reps, weight badge, and active toggle count.
- Mode segmented control:
  - Change weight.
  - Change exercise.
- Toggle checklist:
  - Equipment unavailable.
  - Limited time.
  - Fatigue.
  - Pain or injury.
  - Too easy.
  - Too hard.
  - Technique breakdown.
- Context textarea accepts free text.
- Send button calls AI and appends conversation messages.
- AI response states:
  - Loading.
  - Error alert.
  - Follow-up questions in yellow alert.
  - Ready diff in green alert.
  - Denied response in orange alert.
- Apply button is disabled until response status is ready and proposed exercises exist.
- Applying updates the session and appends the reasoning note.

Session notes helper:

- Entry point: Wand button near session notes.
- Modal title: Help write session notes.
- Prompts the user through textareas:
  - Overall.
  - Technique consistency.
  - Failed sets or RPE.
  - Skipped or missed work.
  - Load mismatch.
  - Planned vs executed.
  - Other.
- Draft Notes button calls AI.
- Generated draft appears in editable Draft textarea.
- Insert button writes the draft into the session notes and closes.

Template max estimation:

- Missing max gate appears when applying a percentage-based template without required maxes.
- Modal lists each missing exercise with numeric estimate input.
- Each row has an `AI Estimate` button.
- Confirm and Apply is disabled until every missing max has a value.

Template AI evaluation:

- Template detail has an AI Analysis side panel.
- Empty state: card with "No evaluation available yet" and Generate AI Evaluation.
- Loading state: loader and "AI is analyzing the program...".
- Completed state: stance badge, summary, strengths, weaknesses, suggestions, and Re-evaluate button.
- Read-only disables generation and re-evaluation.

Analysis AI panels:

- Weekly Analysis loads cached AI reports automatically only in cache-only mode.
- Buttons generate or refresh AI output.
- Exercise ROI Correlation requires at least 4 weeks.
- Program Evaluation appears in Full Block mode and requires at least 4 completed sessions.
- Cached report badge is blue; just-generated report is green; cache miss says "Not generated".
- Generate/Refresh buttons are disabled while loading or read-only.

## Page Specs

### Dashboard

Purpose:

- Main summary of current block status, training progress, maxes, bodyweight, competitions, wellness, lift profiles, and current block analysis.

Structure:

- Page-level stack with responsive metric grids.
- Setup onboarding replaces the dashboard when `needsSetup` is true.
- Cards use bordered `Paper` and `SimpleGrid cols={{ base: 1, md: 2, lg: 3 }}` for dense sections.
- Editable regions use local edit modes with Save/Cancel icons.

Important content:

- Current block identity and phase context.
- Current maxes for squat, bench, deadlift.
- Bodyweight and measurement fields.
- Competition countdown/status cards.
- Phase overview and progress.
- Wellness trend summaries.
- Current block analysis and lift trend table.
- Lift profile cards for squat, bench, deadlift with style notes, sticking points, primary muscle, volume tolerance, and stimulus coefficient.

AI interactions:

- Lift profile review/rewrite/stimulus estimation uses Sparkles/Wand-like actions.
- Profile guide modal supports reviewing or improving lift profile text.
- Loading and disabled states must be represented.

Responsive notes:

- Metric grids collapse to one column on mobile.
- Small tabular sections should use horizontal overflow.
- Editing forms must not exceed screen width.

### Sessions And Session Detail

Use this as the highest-priority mobile redesign area.

Required Figma frames:

- Desktop Sessions Month.
- Desktop Sessions Agenda.
- Mobile Sessions Compact with floating Add button.
- Mobile Session Detail while logging sets.
- Failed set reason modal.
- Auto-regulation modal.
- Video upload modal.
- Notes helper modal.

Session detail mobile priority:

- Keep exercise rows compact.
- Preserve touch targets at least 44px for icon-only controls where possible.
- Keep bottom navigation clear with safe-area spacing.
- Set status controls should fit without horizontal page overflow.
- The user should be able to log sets, failures, RPE, and notes with one hand.

### Analysis

Purpose:

- Analytics workstation with deterministic training metrics plus AI-assisted interpretation.

Top controls:

- Page title and segmented section control:
  - Weekly.
  - Past Blocks.
  - Lifetime Compare.
- Weekly section controls:
  - Window select: Current Week, Previous Week, Previous 2 Weeks, Previous 4 Weeks, Previous 8 Weeks, Full Block.
  - View mode segmented control: Table or Charts.
  - Export Excel.
  - Export Markdown.
  - Regenerate Weekly Analysis.
  - Generated date badge.
  - Pending section count badge.

Weekly content:

- Alerts strip.
- Summary cards:
  - Estimated 1 Rep Maxes.
  - Compliance.
  - Fatigue/readiness style cards.
  - Bodyweight/nutrition/sleep summaries when data exists.
- Raw/table view contains dense tables, badges, and formula explainers.
- Graph view uses Recharts and responsive containers.
- Formula methodology uses nested accordions and code-like formula blocks.

Past Blocks:

- Shows block-level comparisons, past block analysis, start/end maxes, trend, and export/regenerate affordances.

Lifetime Compare:

- Compares long-term trends across blocks and competitions.
- Shows deterministic summary plus AI interpretation when available.

Responsive notes:

- Tables must horizontally scroll on mobile.
- Some columns are hidden below `sm`.
- Chart cards should stack one column on mobile and avoid clipped axis labels.
- Keep section controls wrapping cleanly.

### Program Designer Landing

Purpose:

- Hub for planning tools.

Current layout:

- Title: Program Designer.
- Responsive card grid `base: 1`, `sm: 2`, `lg: 3`.
- Cards are clickable `UnstyledButton` wrappers around bordered Cards.

Cards:

- Phase Design.
- Session Design.
- Plan Templates.
- Import.
- Glossary.
- Competitions.
- Goals.
- Federations.

Card pattern:

- Icon and `lg` title at top.
- Short dimmed description.
- Bottom link-style text "Open ... ->".

### Phase Design

Purpose:

- Manage phases per block.

Content:

- Breadcrumb: Designer / Phase Design.
- Block select.
- Add Phase button.
- Phase cards list name, week range, RPE range, days/week, intent.
- Actions: open Sessions at phase start week, edit, delete.
- Empty state: "No phases defined. Click Add Phase to get started."

Modal:

- Add/Edit Phase modal.
- Fields: name, start week, end week, intent, target RPE min/max, days per week, notes.
- Overlap validation shows error toast.
- Read-only disables editing/deleting.

### Session Designer

Purpose:

- Plan sessions by week before logging them.

Content:

- Week selection and phase context.
- Session cards by day/date.
- Add/edit sessions.
- Planned exercise rows with drag handles.
- Exercise fields: name, sets, reps, load target.
- Load source badge:
  - RPE: blue filled `RPE`.
  - Percentage: green filled `%`.
  - Unresolvable: red filled `?`.
  - Absolute: no badge.
- DND reorder plus up/down buttons.

Responsive notes:

- Keep week controls sticky or easily reachable.
- Planned exercise rows should fit narrow screens by wrapping inputs into two rows.
- Use mobile-friendly drag handles but preserve up/down alternatives.

### Goals, Federations, Competitions, Glossary

Goals:

- Uses separated accordions.
- Each goal opens a dense form with grids up to 4 columns on large screens.
- Needs variants for collapsed, expanded, editing, read-only, empty, and validation states.

Federations:

- Library-style data management for federations and manual qualification standards.
- Design should use compact tables/forms, status badges, and clear add/edit/delete actions.

Competitions:

- Meet planning and results.
- Needs states for future/confirmed/optional/completed/skipped competitions.
- Should support planned attempts and result entry.

Glossary:

- Exercise library for names, primary muscles, categories, and video links.
- Should make search, edit, add, and table scanning easy.

### Import Wizard

Purpose:

- Import training programs, logs, templates, or custom formats from uploaded files.

Stepper:

1. Upload: select file.
2. Classify: template vs log.
3. Glossary: match exercises.
4. Auto-Add: review new glossary entries.
5. Preview: review parsed data.
6. Completed: apply import.

States:

- New upload.
- Import loaded from `import_id` query param.
- Awaiting review.
- Classification override.
- Glossary overrides.
- Auto-add review.
- Preview parsed sessions/templates.
- Apply loading overlay.
- Error state.
- Read-only disables upload/apply.

Figma needs:

- Stepper desktop.
- Stepper mobile where step labels may wrap or become compact.
- Upload dropzone.
- Glossary match table.
- Preview card/grid.
- Final apply confirmation.

### Template Library And Templates

Template library:

- Breadcrumb: Designer / Template Library.
- Buttons: Create Template and Import Template.
- Tabs:
  - Published.
  - My Drafts, disabled in read-only.
  - All.
- Template cards show name, Draft badge, Archived badge, estimated weeks, days/week, created date, author, and View Detail button.
- Empty state: "No templates found. Import one to get started."

Template detail:

- Container size `lg`.
- Header with template name, Draft/Archived badges, weeks and days/week.
- Actions:
  - Publish/Unpublish, only for author and writable.
  - Edit, only for author and writable.
  - Apply Template, writable only.
- Main grid:
  - Left: Sessions and session grid.
  - Right: AI Analysis evaluation panel.

Apply modal:

- Apply strategy select:
  - Create new training block.
  - Append to current block.
  - Replace non-completed sessions.
- Start date picker.
- Week start day select.
- Cancel and Apply actions.
- If missing maxes, close apply modal and open missing max gate.

Template create:

- Narrow form, max width around 600px.
- Fields: name required, description, estimated weeks, days per week.
- Create Template button and Cancel.
- Name validation displays inline error.

Template import:

- Breadcrumb to Template Library.
- Dropzone accepts `.xlsx`, `.xls`, `.csv`.
- Loading overlay while uploading or polling.
- Job status card shows filename, status, errors, Review Draft, and Template Library actions.
- Polls every 3 seconds until succeeded or failed.

Template edit:

- Should include metadata editor, phases editor, sessions editor, session modal variants, and publish/draft states.
- Preserve the same density and nested editor style as current template components.

### Notes

Purpose:

- Dated training context for exports and analysis.

Content:

- Header: Notes and helper description.
- New note card:
  - Date picker.
  - Textarea.
  - Save Entry button.
- Existing notes:
  - Sort newest first.
  - Card preview when not editing.
  - Inline edit mode with date picker, textarea, updated timestamp, save/cancel/delete icons.
- Duplicate dates show error toast.
- Read-only disables add/edit/delete.

### Biometrics And Diet Alias

Purpose:

- Track nutrition, sleep, water, consistency, and recovery context.

Content:

- Header and Add Entry.
- Save button appears only when there are unsaved changes.
- Entries are cards sorted newest first.
- Fields:
  - Date.
  - Average daily calories.
  - Average protein, carbs, fat.
  - Average sleep hours.
  - Water intake and water unit.
  - Consistency and qualitative notes.
- `/diet` uses the same page.

Responsive notes:

- Macro fields use `base: 2`, `sm: 4`.
- Sleep/water/consistency use `base: 1`, `sm: 3`.
- On mobile, numeric inputs need enough width after the iOS input scaling hack.

### Supplements

Purpose:

- Manage supplement phases and peak-week protocols.

Content:

- Header with block select, Save button when dirty, Add Phase button.
- Separated accordion by supplement phase.
- Accordion control includes phase number, editable phase name, item count badge, week range badge.
- Expanded panel includes notes, week range, supplement item rows, and peak-week protocol key/value entries.
- Uses browser prompt for adding a protocol key.
- Read-only disables mutations.

### Rankings

Purpose:

- Compare user lifts and DOTS against OpenPowerlifting filters.

Layout:

- Title and description.
- Dataset loading alert with retry copy.
- Dataset missing alert.
- Grid:
  - Left filter panel on large screens.
  - Results/input panels on the right.
- Filters:
  - Sex, equipment, country, region/state, federation, age class, year, event type, minimum DOTS.
- Lift inputs:
  - Squat, bench, deadlift, bodyweight.
  - Derived total and DOTS preview.
- Analyze button loads percentile/rank results.

Responsive notes:

- Filter panel should stack above results on mobile.
- Long select lists need searchable selects and clearable state.

### Maxes

Purpose:

- Show all-time max table and progress charts.

Content:

- Block or exercise selectors.
- Table with exercise and max, numeric values right-aligned in monospace.
- Charts in `SimpleGrid cols={{ base: 1, lg: 2 }}`.
- Empty/no-data state should explain that maxes come from sessions and stored maxes.

### Tools

Tools landing:

- Title: Tools.
- Responsive card grid `base: 1`, `sm: 2`, `lg: 3`.
- Tool cards use icon, title, description, "Open tool ->".

Tools:

- Plate Calculator: target weight, bar weight, plate inventory, calculated loading per side.
- DOTS Calculator: sex/bodyweight/lifts, calculated total and DOTS.
- Weight Tracker: bodyweight entry/log/chart.
- Percent Table: 1RM input and percentage table.
- Unit Converter: kg/lb bidirectional conversion.
- Attempt Selector: planned attempts based on projected maxes.
- Rankings card links to `/rankings`.

Calculator design:

- Favor compact form panels with result cards.
- Preserve local settings for unit and bar weight.
- Use clear disabled/error states for invalid input.

### Videos

Purpose:

- Review uploaded training videos.

Layout:

- Max width around 672px and centered.
- Header with Film icon, title, and count.
- Filters appear when videos exist:
  - Exercise select.
  - Newest/Oldest toggle button.
- Loading state: centered small loader.
- Empty state:
  - Large Film icon.
  - "No videos uploaded yet".
  - Link to Sessions.
- Feed:
  - Stack of bordered Papers.
  - Each contains `VideoCard`.
- Player:
  - `VideoPlayerModal` opens when a video is selected.

Video card behavior:

- Has hover background transition around 150ms.
- Overlay/actions fade opacity around 150ms.
- Redesign should preserve video thumbnails, metadata, delete state, and modal playback.

### Profiles

Purpose:

- Search public lifter profiles.

Content:

- Header with Users icon and description.
- Search row with text input and Search button.
- Initial load searches with empty query.
- Profile card grid `base: 1`, `sm: 2`, `lg: 3`.
- Card content:
  - Avatar.
  - Display name.
  - `You` badge when self.
  - Nickname.
  - Bio or "No bio yet."
  - Public training summary badge.
- Empty state: bordered paper with "No public profiles found."
- Search failure shows red toast.

### About

Purpose:

- Long-form reference for methodology and formulas.

Design:

- Container `lg`, vertical stack, dividers.
- Header with Activity icon and title "About the Peaking Portal".
- Sections:
  - What this is.
  - How it is built.
  - Data captured and why.
  - Mathematical methodology.
  - Formula cards and tables.
- This is a documentation-heavy page. It can use more prose than operational pages, but should still scan well.

## Component System For Figma

Create reusable Figma components with variants for state and viewport.

App components:

- `AppShell/Desktop`
  - Header 60px.
  - Sidebar 256px.
  - Main content area.
- `AppShell/Mobile`
  - Header 60px.
  - Fixed bottom nav.
  - Safe-area bottom spacing.
- `TopBar/VersionSelector`
  - Normal, loading, archived, empty versions.
- `Sidebar/NavItem`
  - Active, inactive, disabled if a route is unavailable.
- `MobileBottomNav/Item`
  - Active filled, inactive subtle, More menu trigger.
- `ReadOnlyBanner`
  - Visible and hidden states.
- `SettingsDrawer`
  - Signed out, loading, signed in private profile, signed in public profile, read-only.

Data components:

- `MetricCard`
  - Icon, label, value, subvalue, trend.
  - States: good/caution/error/neutral/no data.
- `StatusBadge`
  - Completed, failed, skipped, pending, archived, draft, cached, generated, insufficient data.
- `PhaseBadge`
  - Filled and left-border usage.
- `DataTable`
  - Desktop full columns.
  - Mobile hidden columns plus horizontal overflow.
- `ChartPanel`
  - Loading, empty, populated, insufficient data.
- `AlertStrip`
  - Info, warning, error, success.
- `EmptyState`
  - Icon, title, helper text, optional action.
- `LoadingState`
  - Inline loader, page loader, loading overlay.

Input components:

- `FormSection`
  - Title, helper text, grouped fields.
- `TextInput/Numeric`
  - Unit suffix, invalid, disabled, read-only.
- `DatePickerInput`
  - Normal, disabled.
- `SegmentedControl`
  - 2-option and 3-option variants.
- `Select`
  - Searchable, clearable, disabled, empty options.
- `Textarea`
  - Autosize note-taking variant.
- `Slider/Wellness`
  - 1 to 5 with label and value.
- `CheckboxGroup/FailureReasons`
  - Multi-select in modal.

Action components:

- `PrimaryButton`
  - Default, loading, disabled, destructive, read-only disabled.
- `IconButton`
  - Save, delete, edit, close, back, refresh, upload, settings, AI, toolkit.
- `AIActionButton`
  - Generate, Refresh, Re-evaluate, Draft Notes, Auto-regulate, AI Estimate.
  - States: idle, loading, cached, generated, disabled, error.
- `FloatingActionButton`
  - Mobile Add Session above bottom nav.
- `Toast`
  - Success, warning, error.

Overlay components:

- `Drawer/Settings`.
- `Drawer/Session` for legacy drawer mode.
- `Modal/ConfirmDiscard`.
- `Modal/FailedSetReasons`.
- `Modal/AutoRegulation`.
- `Modal/SessionNotesHelper`.
- `Modal/VideoUpload`.
- `Modal/TemplateApply`.
- `Modal/MissingMaxes`.
- `Modal/PhaseEditor`.
- `Modal/TemplateSessionEditor`.

Session components:

- `SessionRow/Agenda`
  - Completed, planned, closest-to-today, compact.
- `SessionWeek/Compact`
  - Collapsed, expanded.
- `ExerciseLogCard`
  - Normal, dragging, read-only, failed set present, mobile action menu.
- `SetStatusControl`
  - Pending, completed, failed, skipped.
- `WellnessPanel`
  - Record, skip.
- `VideoGrid`
  - Empty, populated.

Template/import components:

- `TemplateCard`
  - Published, draft, archived.
- `TemplateDetailHeader`
  - Owner editable vs viewer read-only.
- `EvaluationPanel`
  - Empty, loading, completed, read-only.
- `ImportStepper`
  - Active step, completed, error.
- `Dropzone`
  - Idle, drag-active, uploading, disabled.

## Responsive Behavior

Breakpoints:

- Mantine `md` controls shell nav switch.
- Many grids use `base`, `sm`, `md`, `lg`, and `xl` responsive column configs.
- Redesign should define explicit desktop, tablet, and mobile frames.

Desktop:

- Header plus left sidebar.
- Most pages use max-width only where content benefits from it, such as Videos and Session Detail.
- Analytics and Dashboard should use multi-column metric grids.
- Tables can show all columns.
- Modals can be `md` or `lg`; drawers can be right-aligned.

Tablet:

- Sidebar may collapse depending on `md` breakpoint.
- Two-column grids should be preferred where space allows.
- Avoid making tables too narrow; use overflow wrappers.
- Keep top controls wrapped into multiple rows rather than shrinking text.

Mobile:

- Bottom nav is always visible below `md`.
- Main content must clear bottom nav and safe area.
- Use one-column page flow except compact metrics that can safely use two columns.
- Long tables scroll horizontally or convert to stacked cards.
- Hide lower-priority columns with `visibleFrom="sm"` and provide card equivalents when needed.
- Floating add actions must sit above bottom nav and browser overlap.
- Inputs must avoid iOS focus zoom and must not overflow their grid cells.
- Avoid fixed-width controls wider than the viewport; selects and date inputs should become full-width where needed.

Existing mobile-specific behavior to preserve:

- React Big Calendar toolbar wraps below 639px.
- Calendar buttons shrink below 639px.
- Agenda table cells allow wrapping below 639px.
- Mantine text/select/autocomplete/date inputs use 16px plus scale hack below 639px.
- Custom scrollbars support horizontal table/chart overflow.

## Interaction And Transition Model

Current transitions are mostly Mantine defaults plus a few explicit microinteractions.

Expected default transitions:

- Menus open from triggers with Mantine menu animation.
- Modals fade/scale using Mantine defaults.
- Drawers slide from the right.
- Loading buttons swap label/disabled state and show spinner.
- Notifications slide/fade in the top-right.
- Segmented controls change immediately and often update query params.
- Tabs switch immediately.
- Accordions expand/collapse with Mantine defaults.

Explicit interactions:

- Drag/drop exercise rows use dnd-kit transform and transition.
- Dragged rows have opacity 0.5 and high z-index.
- Video card hover background transitions around 150ms.
- Video overlay actions fade opacity around 150ms.
- Refresh icons may spin with CSS animation while loading.
- Upload progress uses an animated Mantine Progress bar.

Redesign guidance:

- Keep transitions functional and restrained.
- Avoid long animations that slow training logging.
- Use motion to confirm state changes: save, generate, upload, apply, add/remove, expand/collapse.
- AI generation should show clear loading and completion state. Do not make users guess whether a button triggered a background job.

## Important State Permutations

Create Figma variants or annotated examples for these combinations:

- Signed out read-only with public data.
- Signed in writable user.
- Auth loading.
- Auth callback success/loading/failure.
- Setup required with read-only sign-in prompt.
- Setup required signed in with blank/manual/template options.
- Template setup blocked by missing maxes.
- Active program version.
- Archived program version.
- Multiple program versions.
- No sessions.
- Many sessions across multiple blocks.
- Session planned.
- Session completed.
- Session with failed sets and failed reasons.
- Session dirty/autosaving/saved/save failed.
- Session read-only.
- Wellness skipped.
- Wellness recorded.
- Video upload idle/file selected/uploading/error/success.
- AI report cache miss.
- AI report cached.
- AI generation loading.
- AI generation error.
- AI response insufficient data.
- Import no file/uploading/awaiting review/preview/applying/error.
- Template published/draft/archived.
- Template owned editable vs non-owner read-only.
- Empty tables/charts.
- Dataset loading or not found in Rankings.
- Mobile keyboard open with bottom browser overlap.

## Figma Redesign Deliverables

Minimum frames:

- Desktop app shell with Dashboard.
- Mobile app shell with bottom nav.
- Settings drawer signed out.
- Settings drawer signed in with public profile controls.
- Login page with error state.
- Setup onboarding signed in with template missing-max gate.
- Sessions Month desktop.
- Sessions Agenda desktop.
- Sessions Compact mobile.
- Session Detail mobile logging flow.
- Failed Set Reasons modal.
- Auto-regulation modal with ready AI diff.
- Session Notes Helper modal with generated draft.
- Video Upload modal uploading.
- Analysis Weekly table view desktop.
- Analysis Weekly chart view desktop.
- Analysis mobile with controls wrapped and table overflow/card alternatives.
- Past Blocks analysis.
- Lifetime Compare.
- Designer Landing.
- Phase Design with Add/Edit modal.
- Session Designer with planned exercise drag state.
- Import Wizard through all steps.
- Template Library.
- Template Detail with AI evaluation.
- Apply Template plus Missing Maxes gate.
- Notes page.
- Biometrics page.
- Supplements accordion.
- Rankings filter/results page.
- Tools launcher and at least one calculator detail.
- Videos feed and player modal.
- Profiles search.
- About methodology page.

Required component variants:

- Buttons: default, hover, active, loading, disabled, read-only disabled, destructive.
- Icon buttons: default, hover, active, disabled.
- Badges: status, AI cache, phase, draft, archived, failed set, load type.
- Form fields: default, focused, error, disabled, read-only, with unit suffix.
- Table rows: normal, hover, selected/clickable, empty.
- Cards/Papers: normal, hover-clickable, active, disabled/read-only.
- Modals: default, loading, error, confirm destructive.
- Drawers: settings and session.
- Toasts: success, warning, error.
- Loading/empty/error panels.

Annotations the Figma AI should include:

- Route path for each page frame.
- Which controls mutate data and are disabled in read-only.
- Which controls update URL query params.
- Which actions call AI.
- Which UI states are cache-only vs generated.
- Which tables scroll horizontally on mobile.
- Which mobile actions are moved into menus or floating buttons.
- Safe-area and bottom nav spacing rules.

## Known Current Design And Routing Notes

- `/charts` is present in the desktop sidebar but has no route in `App.tsx`.
- `/diet` is an alias to `BiometricsPage`, not a separate diet page.
- `/calendar` and `/list` are redirects, not separate maintained pages.
- Login and auth callback currently render inside the global app shell because `AppShell` wraps all routes.
- Browser `prompt(...)` is still used for Convert to Template and supplement protocol key naming. A redesign could replace these with modal forms, but the underlying flow should stay the same.
- Some pages use long dense tables. A redesign should improve mobile treatment without removing detail.
- Read-only mode is a core product state, not an edge case.

## Redesign Guardrails

- Do not remove data density. Improve grouping and hierarchy instead.
- Do not hide important training status behind decorative cards.
- Do not make the Dashboard a landing page. It is an operational overview.
- Do not make Sessions depend on desktop-only interactions. Phone logging is critical.
- Do not collapse AI states into a single generic spinner. Cache miss, cached, generating, generated, insufficient data, denied, and error states mean different things.
- Do not remove read-only indicators or disabled states.
- Preserve units, bodyweight, sex, week start, bar weight, and default sessions view as user-controlled settings.
- Preserve phase colors and status badges as scanning aids.
- Preserve direct routes for deep links to sessions, template detail/edit, and lift profiles.

