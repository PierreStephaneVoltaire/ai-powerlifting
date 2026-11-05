# Project Structure

Annotated map of `utils/powerlifting-app/`. The authoritative, line-by-line
implementation reference lives in [`docs/REFERENCE.md`](docs/REFERENCE.md) —
this file is the orientation guide.

```
powerlifting-app/
├── src/package.json         Workspace root (workspaces: dependencies/types, backend, frontend), plus package-lock.json, tsconfig.json, pytest.ini
├── src/backend/             Express API — thin transport layer over the typed services
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── server.ts        Express app assembly, middleware order, route mounting
│       ├── routes/          One file per REST domain (programs, sessions, analytics, videos, …)
│       ├── controllers/     Route handlers + DynamoDB access (one per domain)
│       ├── db/
│       │   ├── dynamo.ts    Document client + table/bucket name resolution
│       │   ├── transforms.ts DynamoDB item ⇄ typed object conversions
│       │   └── schema_*.json  Canonical JSON shapes (program, glossary, markers)
│       ├── middleware/
│       │   ├── auth.ts       mapped_pk resolution + read/write gating
│       │   ├── validate.ts   request body validation
│       │   └── errorHandler.ts centralized AppError handling
│       ├── services/        Cross-route business logic
│       │   ├── blockAnalytics.ts      Past-Blocks + Compare analytics orchestration
│       │   ├── blockAnalysisExport.ts  Per-block xlsx/markdown exports
│       │   ├── analysisCache.ts       Section/window caching + regeneration
│       │   ├── sessionStore.ts        Session table read/merge into Program
│       │   ├── userSettings.ts        if-user profile/settings reads
│       │   └── masterCopy.ts          Operator→test data copy helper
│       └── utils/
│           ├── agent.ts      invokeToolDirect → Coach jobs (AI operations)
│           ├── operations.ts  callOperation → typed operation on the owning pl-<domain> service
│           ├── operationCache.ts  In-process LRU cache + write invalidation (math/read TTLs; writes bypass + invalidate)
│           ├── logger.ts     pino logger
│           ├── countries.ts  ISO country resolution (competitions)
│           └── videoSort.ts  Video ordering helpers
├── src/frontend/               React 19 + Vite PWA (Mantine 9, Tailwind, Zustand)
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.tsx          App entry
│       ├── App.tsx           Routes (single source for the route table)
│       ├── api/              Axios clients (client, analytics, profiles, settings)
│       ├── auth/AuthProvider.tsx  Discord OAuth context
│       ├── pages/            ~30 route components (Dashboard, AnalysisPage, CalendarPage, …)
│       ├── components/       Feature-grouped UI
│       │   ├── layout/       AppShell, TopBar, Sidebar, SettingsDrawer
│       │   ├── analysis/     WeeklyData, AiAnalysis, BlockAnalytics, PeakingTimeline, …
│       │   ├── sessions/     SessionDrawer, RestTimer*, VideoGrid, AutoRegulationModal, …
│       │   ├── templates/    Template editor, ApplyModal, EvaluationPanel, SessionGrid, …
│       │   ├── import/       Import wizard steps (Upload → Classify → Glossary → Preview → Apply)
│       │   ├── tools/        PlateCalculator, DotsCalculator, AttemptSelector, …
│       │   ├── charts/       Recharts wrappers (Volume, Intensity, Weight, StrengthProgress, …)
│       │   ├── glossary/     ExerciseMuscleMap
│       │   ├── videos/       VideoCard, VideoPlayerModal
│       │   ├── setup/        SetupOnboarding
│       │   └── shared/       Num, LoadTypeBadge, ReadOnlyBanner
│       ├── store/            Zustand stores (program, settings, budget, federation, competitions, ui, restTimer)
│       ├── utils/            Pure helpers (rpe, volume, units, plates, dots, ipfGl, dates, muscles, …)
│       └── constants/
│           ├── formulaDescriptions.ts  Human-facing formula prose (mirrors the math)
│           └── plates.ts                Plate inventory constants
├── src/dependencies/types/         Shared TypeScript types (@powerlifting/types)
│   ├── package.json
│   ├── tsconfig.json
│   └── index.ts             Program, Session, Exercise, Competition, Glossary, Budget, …
├── src/services/
│   ├── handlers/             Domain operation packages grouped by service
│   ├── lib/                  Shared stores, scoping, calculations, and AI prompts
│   ├── operations/           Typed HTTP/MCP operation manifests
├── src/lambda/
│   ├── master-sync/          Master data sync AWS Lambda
│   └── video-thumbnail/      S3-triggered thumbnail AWS Lambda
├── docker/                  Container build context
├── terraform/               Main stack, applied by CI (see AGENTS.md)
│   ├── main.tf              Module wiring: ECR, media buckets, CloudFront, DynamoDB, dataset, Lambdas, tunnel
│   ├── modules/             ecr, session_videos, budget_media, cloudfront, powerlifting_dynamodb,
│   │                        powerlifting_dataset, powerlifting_master_sync, video_thumbnail_lambda, tunnel
│   ├── backend.tf           S3 state backend
│   ├── providers.tf, versions.tf, variables.tf, outputs.tf
│   ├── k8s/                 Kubernetes stacks: core, perms (local), network, app (in-cluster runner)
│   └── coach/               Coach and Discord bot workloads (local)
├── docs/
│   ├── ARCHITECTURE.md      Software/technical architecture deep-dive
│   ├── FORMULAS.md          Math-heavy formula breakdown and rationale
│   └── REFERENCE.md         Verbatim copy of the original implementation README
├── README.md               Human-facing readme (this project's front door)
├── PROJECT_STRUCTURE.md     This file
└── AGENTS.md                Stack + contribution guidelines for agents/humans
```

## Sources of truth

When behavior and prose disagree, the code wins. The highest-signal files:

- **Frontend behavior:** `src/frontend/src/App.tsx` (routes),
  `src/frontend/src/pages/AnalysisPage.tsx`,
  `src/frontend/src/components/analysis/WeeklyData.tsx`,
  `src/frontend/src/components/analysis/AiAnalysis.tsx`,
  `src/frontend/src/components/layout/SettingsDrawer.tsx`
- **Formula prose:** `src/frontend/src/constants/formulaDescriptions.ts`
- **Backend routes:** `src/backend/src/routes/analytics.ts`, `src/backend/src/routes/setup.ts`,
  `src/backend/src/routes/settings.ts`, `src/backend/src/routes/profiles.ts`
- **Backend services:** `src/backend/src/services/blockAnalytics.ts`,
  `src/backend/src/services/analysisCache.ts`, `src/backend/src/services/userSettings.ts`
- **Types:** `src/dependencies/types/index.ts`
- **AI plumbing:** `src/backend/src/utils/agent.ts` (invokeToolDirect → Coach jobs)
- **Service plumbing:** `src/backend/src/utils/operations.ts` (callOperation HTTP call to the owning domain service) + `src/backend/src/utils/operationCache.ts` (in-process LRU cache + write invalidation)
- **Service runtime:** `src/services/` handlers and shared `src/services/lib/`, packaged by `docker/powerlifting-services.pkr.hcl`.
- **AWS Lambda substrate:** `powerlifting-app/terraform/` retains only the master-sync and video-thumbnail Lambdas.
- **Infra:** `terraform/` (root, local k3s) and `powerlifting-app/terraform/` (AWS-only)
