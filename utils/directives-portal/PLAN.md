# Directives Portal — Implementation Plan

## Overview

A new portal at `utils/directives-portal/` for managing behavioral directives stored in DynamoDB (`if-core` table, PK=`DIR`). Same tech stack as the powerlifting app: React 19 + Mantine 9 + Tailwind + @dnd-kit + Express backend + Discord OAuth. Backend proxies directive CRUD to the existing FastAPI agent API (`/v1/directives/*`). Domain: `directives.if-prototype.xyz`.

---

## Phase 1: FastAPI Directive CRUD Endpoints ✅ DONE

### What already existed
| Method | Route | Status |
|--------|-------|--------|
| `POST` | `/v1/directives/reload` | ✅ existed |
| `GET` | `/v1/directives` | ✅ existed (but missing `types` in response — **fixed**) |
| `GET` | `/v1/directives/{alpha}/{beta}` | ✅ existed (but missing `types` — **fixed**) |
| `GET` | `/v1/directives/{alpha}/{beta}/history` | ✅ existed |

### What was added
| Method | Route | Status |
|--------|-------|--------|
| `POST` | `/v1/directives/` | ✅ added — creates directive, auto-assigns beta |
| `PUT` | `/v1/directives/{alpha}/{beta}` | ✅ added — revises directive (new version) |
| `PUT` | `/v1/directives/{alpha}/{beta}/reorder` | ✅ added — changes alpha/beta numbers |
| `DELETE` | `/v1/directives/{alpha}/{beta}` | ✅ added — deactivates directive (soft delete) |

### Changes made to existing files
1. **`app/src/api/directives.py`** — Rewrote entirely:
   - Added Pydantic request models: `CreateDirectiveRequest`, `ReviseDirectiveRequest`, `ReorderDirectiveRequest`
   - Added `_directive_to_dict()` helper that includes `types` field (was missing)
   - Added `POST /` (create), `PUT /{alpha}/{beta}` (revise), `PUT /{alpha}/{beta}/reorder` (reorder), `DELETE /{alpha}/{beta}` (deactivate)

2. **`app/src/storage/directive_store.py`** — Bug fix:
   - `revise()` method now preserves `types` when creating new version: `types=types if types is not None else existing.types` (line 316)
   - Previously, revised directives would lose their types

---

## Phase 2: Directives Portal — Backend ⬜ TODO

### Architecture
- Express 5 server on port 3006
- Discord OAuth2 (same pattern as powerlifting app)
- Strict auth: **all** routes require authentication (no read-only mode)
- Proxy `/api/directives/*` to FastAPI agent API at `IF_AGENT_API_URL` (env var)

### File listing

```
utils/directives-portal/backend/
├── package.json              ✅ DONE
├── tsconfig.json             ✅ DONE
└── src/
    ├── server.ts              ⬜ Express entry, middleware wiring, proxy setup
    ├── routes/
    │   └── auth.ts            ⬜ GET /discord/login, GET /discord/callback, GET /me, POST /logout
    ├── controllers/
    │   └── authController.ts  ⬜ Discord OAuth flow (exchange code, JWT sign/verify)
    ├── middleware/
    │   ├── auth.ts            ⬜ JWT verification + requireAuth (strict — 401 if no auth)
    │   └── errorHandler.ts   ✅ DONE — AppError class + error handler
    └── utils/
        └── logger.ts          ⬜ Pino logger
```

### Backend API routes

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| `GET` | `/api/auth/discord/login` | No | Redirect to Discord OAuth |
| `GET` | `/api/auth/discord/callback` | No | OAuth callback → set JWT cookie |
| `GET` | `/api/auth/me` | No | Check auth status |
| `POST` | `/api/auth/logout` | No | Clear cookie |
| `*` | `/api/directives/*` | Yes | Proxied to FastAPI `/v1/directives/*` |

### Auth middleware (strict mode)

Unlike the powerlifting app (which has `requireUserOptional` + read-only mode), the directives portal uses `requireAuth` which:
- Checks for `dir_auth` cookie (JWT)
- If missing/invalid → returns 401
- If valid → sets `req.user` and proceeds
- All `/api/directives/*` routes go through this

### Proxy logic

The proxy forwards `/api/directives/*` to `{IF_AGENT_API_URL}/v1/directives/*`:
- Preserves method, headers, body, query params
- Strips `/api` prefix → replaces with `/v1`
- Example: `GET /api/directives/` → `GET {IF_AGENT_API_URL}/v1/directives/`
- Example: `PUT /api/directives/0/1/reorder` → `PUT {IF_AGENT_API_URL}/v1/directives/0/1/reorder`

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3006` | Backend port |
| `IF_AGENT_API_URL` | `http://if-agent-api:8000` | FastAPI agent API URL (in-cluster) |
| `DISCORD_CLIENT_ID` | required | Discord OAuth client ID |
| `DISCORD_CLIENT_SECRET` | required | Discord OAuth client secret |
| `DISCORD_REDIRECT_URI` | required | OAuth callback URL |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for redirects |
| `JWT_SECRET` | `dev-secret-change-me` | JWT signing secret |
| `COOKIE_DOMAIN` | `` | Cookie domain |
| `COOKIE_SECURE` | `true` | Secure cookie flag |
| `AWS_REGION` | `ca-central-1` | AWS region |

### Cookie naming: `dir_auth` (not `pl_auth`) to avoid conflicts

### Key backend source code patterns

#### `middleware/auth.ts`
- `signToken(payload)`, `verifyToken(token)`, `signState()`, `verifyState(state)` — same as powerlifting
- `requireAuth` middleware — strict: returns 401 `AUTH_REQUIRED` if no `dir_auth` cookie
- No `requireUserOptional`, no `readOnly` mode, no `mapped_pk` resolution

#### `controllers/authController.ts`
- `discordLogin` — redirects to Discord OAuth with signed state
- `discordCallback` — exchanges code for Discord token, fetches user, signs JWT, sets `dir_auth` cookie
- `getMe` — returns `{ user, authenticated }`
- `logout` — clears `dir_auth` cookie

#### `server.ts`
- Mounts auth routes at `/api/auth`
- Applies `requireAuth` to `/api/directives`
- Uses `http-proxy-middleware` to proxy `/api/directives` → `{IF_AGENT_API_URL}/v1/directives`
- Path rewrite: `^/api/directives` → `/v1/directives`

---

## Phase 3: Directives Portal — Frontend ⬜ TODO

### Architecture
- React 19 + Mantine 9 + Tailwind 3 + @dnd-kit
- Vite dev server with proxy to backend
- Strict auth: entire app is gated behind Discord login
- Zustand store for directive state

### File listing

```
utils/directives-portal/frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── index.html
└── src/
    ├── main.tsx              # Mantine + React mount
    ├── App.tsx               # Routes + auth gate
    ├── index.css              # Tailwind imports + Mantine CSS
    ├── auth/
    │   └── AuthProvider.tsx  # Auth context (strict — null = not signed in)
    ├── api/
    │   └── client.ts         # Axios client + directive API functions
    ├── store/
    │   └── directivesStore.ts # Zustand: directives list, loading, CRUD actions
    ├── pages/
    │   ├── LoginPage.tsx     # Discord sign-in gate
    │   ├── DirectivesPage.tsx # Main directives view (tier columns + cards)
    │   └── AuthCallbackPage.tsx # OAuth callback handler
    └── components/
        ├── DirectiveCard.tsx  # Individual directive card (draggable)
        ├── TierColumn.tsx     # Column for one alpha tier (sortable container)
        ├── DirectiveDetailModal.tsx # Expand/edit directive content
        ├── NewDirectiveModal.tsx # Create new directive form
        └── TypeBadge.tsx      # Directive type tag (e.g., "core", "code")
```

### Frontend packages

```
@dnd-kit/core ^6.0.0, @dnd-kit/sortable ^8.0.0, @dnd-kit/utilities ^3.0.0
@mantine/core ^9.0.1, @mantine/form ^9.0.1, @mantine/hooks ^9.0.1, @mantine/notifications ^9.0.1
axios ^1.6.0, lucide-react ^0.300.0, react ^19.2.5, react-dom ^19.2.5
react-router-dom ^6.20.0, zustand ^4.4.0
```

### UI Layout

**Main page (`DirectivesPage.tsx`)**:
- Top bar: "IF Directives" title + user avatar/sign out + "New Directive" button
- 6 tier columns (Tier 0–5) arranged horizontally
- Each column header with tier label + color coding:
  - Tier 0: Red (Fundamental — Never break)
  - Tier 1: Orange (Critical — Only bypass with explicit request)
  - Tier 2: Yellow (Standard — Recommended)
  - Tier 3: Blue (Preference — Optional but encouraged)
  - Tier 4: Teal (Advisory — Consider)
  - Tier 5: Gray (Notes — Background context)
- Each column contains `DirectiveCard` components, vertically sorted by beta

**DirectiveCard**:
- Shows `alpha-beta` ID (e.g., "0-1"), label, content preview (truncated)
- Type badges (small colored pills for "core", "code", "health", etc.)
- Drag handle for reordering
- Click to open `DirectiveDetailModal`
- Delete button (with confirmation)

**Drag-and-drop flow**:
1. User drags a card from one tier column to another (or within same column)
2. On drop, calculate new alpha (from target column) and new beta (from drop position)
3. Call `PUT /api/directives/{alpha}/{beta}/reorder` with `{new_alpha, new_beta}`
4. Refresh directive list from API

**NewDirectiveModal**:
- Form: alpha tier (0-5 dropdown), label, content (textarea), types (tag input)
- On submit: `POST /api/directives/`
- Beta is auto-assigned by the backend

**DirectiveDetailModal**:
- Shows full content, version, created_at, types
- Edit mode: textarea for content, text input for label, tag input for types
- Save: `PUT /api/directives/{alpha}/{beta}` (creates new version)
- Delete: `DELETE /api/directives/{alpha}/{beta}` (deactivates)

### Auth gate

The `App.tsx` renders differently based on auth state:
- `loading` → full-page spinner
- `!user` → `<LoginPage />` only (no sidebar, no app shell)
- `user` → `<DirectivesPage />` with top bar

### AuthProvider (strict)

```typescript
interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  signIn: () => void
  signOut: () => Promise<void>
}
```

No `mapped_pk` or `readOnly` — just user/null.

### API client functions

```typescript
fetchDirectives(alpha?: number): Promise<Directive[]>
fetchDirective(alpha, beta): Promise<Directive>
createDirective(data): Promise<Directive>
reviseDirective(alpha, beta, data): Promise<Directive>
reorderDirective(alpha, beta, newAlpha, newBeta): Promise<Directive>
deleteDirective(alpha, beta): Promise<void>
fetchDirectiveHistory(alpha, beta): Promise<DirectiveVersion[]>
```

### Zustand store

```typescript
interface DirectivesStore {
  directives: Directive[]
  loading: boolean
  error: string | null
  fetchAll: () => Promise<void>
  create: (data) => Promise<void>
  revise: (alpha, beta, data) => Promise<void>
  reorder: (alpha, beta, newAlpha, newBeta) => Promise<void>
  remove: (alpha, beta) => Promise<void>
}
```

### Mantine theme

Primary color: `violet`. Same font families as powerlifting app (DM Sans, Barlow Condensed, IBM Plex Mono).

### Tier CSS variables

```
light: tier-0=#fef2f2 tier-1=#fff7ed tier-2=#fefce8 tier-3=#eff6ff tier-4=#f0fdfa tier-5=#f9fafb
dark:  tier-0=#1a0f0f tier-1=#1a150e tier-2=#1a1a0e tier-3=#0e1520 tier-4=#0e1a18 tier-5=#151618
```

---

## Phase 4: Terraform Updates ⬜ TODO

### What the existing system does automatically

The Terraform config at `terraform/locals.tf` scans `utils/*/domain.yaml` and:
- Creates Cloudflare DNS CNAME records for each app with a `domain` field
- Creates tunnel ingress rules for each app
- Creates HTTPRoutes per domain (hostname-based routing)

So adding `utils/directives-portal/domain.yaml` with `domain: directives.if-prototype.xyz` will automatically create:
- `cloudflare_zone.managed["if-prototype.xyz"]` (if zone doesn't exist yet)
- `cloudflare_record.tunnel_cname["directives-portal"]`
- Tunnel ingress rule for `directives.if-prototype.xyz`
- `kubectl_manifest.route_per_domain["directives-portal"]` HTTPRoute

### Manual Terraform changes needed

1. **`terraform/k8s-deployments.tf`** — Add to `local.portals` (around line 256):
   ```hcl
   directives-portal = {
     port     = 3006
     has_db   = true
     db_table = "if-core"
   }
   ```

2. **`terraform/locals.tf`** — Add to `local.portal_backend_ports` (around line 30):
   ```hcl
   "directives-portal" = 3006
   ```

3. **`terraform/image.tf`** — Add ECR repos:
   - Add `"directives-portal-backend"` to `portal_backends` set (around line 16)
   - Add `"directives-portal-frontend"` to `portal_frontends` set (around line 33)
   - Add `"directives-portal" = "/api"` to `local.portal_api_paths` (around line 98)

4. **ConfigMap** (wherever portal configs are defined) — Add `directives-portal-config` with:
   ```
   IF_AGENT_API_URL = "http://if-agent-api:8000"
   DISCORD_CLIENT_ID = (from var)
   DISCORD_CLIENT_SECRET = (from var)
   DISCORD_REDIRECT_URI = "https://directives.if-prototype.xyz/api/auth/discord/callback"
   FRONTEND_URL = "https://directives.if-prototype.xyz"
   JWT_SECRET = (from var)
   COOKIE_DOMAIN = ".if-prototype.xyz"
   COOKIE_SECURE = "true"
   AWS_REGION = (from var)
   ```

5. **`terraform/variables.tf`** — `discord_client_id`, `discord_client_secret`, `discord_redirect_uri`, `jwt_secret` already exist for the powerlifting app. The directives portal ConfigMap can reference the same variables.

### What NOT to change
- Do NOT run `terraform apply`
- Only run `terraform fmt`, `terraform validate`, `terraform plan`

---

## Phase 5: Docker / Build ⬜ TODO

The existing Packer build system at `docker/portals-backend.pkr.hcl` and `docker/portals-frontend.pkr.hcl` already iterates over `local.portals`, so adding `directives-portal` to the `portals` local will automatically create Docker images for:
- `if-directives-portal-backend`
- `if-directives-portal-frontend`

No changes needed to Packer configs.

---

## Implementation Order

1. ✅ Phase 1: FastAPI CRUD endpoints (DONE)
2. ⬜ Phase 2: Backend (auth + proxy)
3. ⬜ Phase 3: Frontend (full React app)
4. ⬜ Phase 4: Terraform updates
5. ⬜ Phase 5: Docker/build verification
6. ⬜ Test: `npm run build` in both frontend and backend
7. ⬜ Test: Typecheck passes

---

## Key Decisions

1. **Proxy vs direct DynamoDB**: Backend proxies to FastAPI instead of reading DynamoDB directly. This reuses the existing `DirectiveStore` with all its versioning logic, caching, and validation. The portal backend only handles auth + proxying.

2. **Strict auth**: Unlike the powerlifting app (which has read-only mode for unauthenticated users), the directives portal requires authentication for everything. Directives are sensitive — they control agent behavior.

3. **Cookie naming**: `dir_auth` instead of `pl_auth` to avoid cookie conflicts.

4. **Reorder logic**: Changing a directive's position deactivates the old one and creates a new one at the target position. This preserves audit history. The frontend must refresh after reorder to get the new beta assignment.

5. **Types field**: The existing API was missing the `types`/`dtype` field in responses. This is now included via `_directive_to_dict()`.

6. **DnD kit**: Using `@dnd-kit/core` + `@dnd-kit/sortable` for drag-and-drop, same library already proven in the powerlifting frontend.

7. **Tier colors**: Each tier column has a distinct background color for quick visual identification of priority levels.

8. **Domain**: `directives.if-prototype.xyz` — the `if-prototype.xyz` zone will be auto-created by Terraform if it doesn't exist. After first `terraform apply`, update nameservers at Namecheap to the Cloudflare nameservers from the Terraform output.
