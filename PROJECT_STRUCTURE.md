# Project Structure

Annotated map of `utils/powerlifting-app/`. The authoritative, line-by-line
implementation reference lives in [`docs/REFERENCE.md`](docs/REFERENCE.md) —
this file is the orientation guide.

```
powerlifting-app/
├── backend/                 Express API — thin transport layer (delegates to IF Agent API)
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
│           ├── agent.ts      invokeToolDirect / invokeChat → IF Agent API (health_rag_search only)
│           ├── lambda.ts    invokeLambda → HTTP API Gateway per-tool POST (94 health tools)
│           ├── lambdaCache.ts  In-process LRU cache + write invalidation (math/read TTLs; writes bypass + invalidate)
│           ├── logger.ts     pino logger
│           ├── countries.ts  ISO country resolution (competitions)
│           └── videoSort.ts  Video ordering helpers
├── frontend/               React 19 + Vite PWA (Mantine 9, Tailwind, Zustand)
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
├── packages/types/         Shared TypeScript types (@powerlifting/types)
│   ├── package.json
│   ├── tsconfig.json
│   └── index.ts             Program, Session, Exercise, Competition, Glossary, Budget, …
├── lambda/
│   ├── master-sync/         Master data sync Lambda (handler.py)
│   ├── video-thumbnail/     S3-triggered video-thumbnail generator (index.py, Python 3.12 + ffmpeg layer)
│   ├── <tool-name>/         One AWS Lambda per health tool (94 total — e.g. health_get_program, weekly_analysis, fatigue_profile_estimate); handler.py + config.py + resources.yaml each
│   ├── pl_authorizer/       API Gateway request-authorizer Lambda (X-Internal-Token gate)
│   ├── tool_registry/       Serves GET /openapi.json from resources.json (94 tools' descriptions + input schemas)
│   └── layers/              10 AWS Lambda layers shared by all 94 health tools (pl-ai, pl-boto3, pl-pandas, pl-program, pl-sessions, pl-templates, pl-glossary, pl-imports, pl-federation, pl-analysis-cache)
├── docker/                  Container build context
├── terraform/               Powerlifting-specific AWS resources (see AGENTS.md)
│   ├── main.tf              ECR repos + lifecycle policy
│   ├── videos.tf            S3 video bucket + video-thumbnail Lambda + ffmpeg layer + S3 trigger
│   ├── budget.tf            Budget media S3 bucket + if-powerlifting-budget DynamoDB table
│   ├── cloudfront.tf        CloudFront distribution for media
│   ├── backend.tf           S3 state backend (separate key from root stack)
│   ├── lambda.tf            94 health-tool Lambdas (for_each over lambda/<tool>/ folders) + shared common env (model defaults, DynamoDB table refs, OpenRouter creds from SSM)
│   ├── layers.tf            10 AWS Lambda layer versions (pl-ai, pl-boto3, pl-pandas, pl-program, pl-sessions, pl-templates, pl-glossary, pl-imports, pl-federation, pl-analysis-cache)
│   ├── apigateway.tf        HTTP API Gateway + per-tool POST /<tool> routes (authorization_type=CUSTOM, wired to authorizer.tf)
│   ├── authorizer.tf        pl_authorizer Lambda + aws_apigatewayv2_authorizer.pl_internal + integration + permission
│   ├── ssm.tf               Plain-String aws_ssm_parameter (OPENROUTER_API_KEY, INTERNAL_API_TOKEN — no KMS) + data.aws_ssm_parameter sources for both
│   ├── iam.tf               IAM exec role shared by all pl-* Lambdas (logs, DynamoDB, S3 if needed)
│   ├── variables.tf         Region, ECR prefix, DynamoDB table names, OPENROUTER_API_KEY, INTERNAL_API_TOKEN
│   ├── versions.tf          Provider versions
│   └── outputs.tf
├── domain.yaml              Domain config
├── package.json             Workspace root (workspaces: packages/types, backend, frontend)
├── tsconfig.json
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

- **Frontend behavior:** `frontend/src/App.tsx` (routes),
  `frontend/src/pages/AnalysisPage.tsx`,
  `frontend/src/components/analysis/WeeklyData.tsx`,
  `frontend/src/components/analysis/AiAnalysis.tsx`,
  `frontend/src/components/layout/SettingsDrawer.tsx`
- **Formula prose:** `frontend/src/constants/formulaDescriptions.ts`
- **Backend routes:** `backend/src/routes/analytics.ts`, `backend/src/routes/setup.ts`,
  `backend/src/routes/settings.ts`, `backend/src/routes/profiles.ts`
- **Backend services:** `backend/src/services/blockAnalytics.ts`,
  `backend/src/services/analysisCache.ts`, `backend/src/services/userSettings.ts`
- **Types:** `packages/types/index.ts`
- **Agent plumbing:** `backend/src/utils/agent.ts` (invokeToolDirect → IF Agent API; still used for `health_rag_search`)
- **Lambda plumbing:** `backend/src/utils/lambda.ts` (invokeLambda HTTP wrapper against the API Gateway) + `backend/src/utils/lambdaCache.ts` (in-process LRU cache + write invalidation)
- **Lambda substrate:** `powerlifting-app/terraform/lambda.tf` + `layers.tf` + `apigateway.tf` + `authorizer.tf` + `ssm.tf` (94 health-tool functions, pl_authorizer, HTTP API Gateway, 10 Lambda layers, plain-string SSM params)
- **Infra:** `terraform/` (root, local k3s) and `powerlifting-app/terraform/` (AWS-only)
