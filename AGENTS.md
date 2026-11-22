# Powerlifting Meet-Prep Portal (NoLift)

Competition-geared meet-prep portal for powerlifters. Domain terms in
[CONTEXT.md](CONTEXT.md); decisions in [docs/adr/](docs/adr/). Read both before
working — this file is only layout + operating rules.

## Layout

- `src/frontend/` — React + Vite app
- `src/backend/` — Express API (Node)
- `src/services/` — eighteen typed HTTP/MCP domain services; one folder per service (`<domain>/` plus shared `runtime/`),
  with manifests in `operations/`.
- `src/lambda/` — the retained `video-thumbnail` and `master-sync` AWS Lambdas only.
- `terraform/` — AWS and Cloudflare (applied by CI), plus `k8s/` and `coach/`
  Kubernetes stacks (see "Terraform scopes" below).

## Terraform scopes — do not cross them

- `powerlifting-app/terraform/` → AWS resources only, applied by CI.
- `powerlifting-app/terraform/k8s/{core,perms,network,mesh,app}` → the Powerlifting Kubernetes resources, one state each, applied by the in-cluster runner.
- `powerlifting-app/terraform/coach/` → its own state for the Coach Kubernetes resources (PVC, Deployments, Services), applied by the same runner. Coach ECR repositories live in `powerlifting-app/terraform/` with the other AWS resources. See [Coach](src/services/coach/README.md).

Keep infrastructure deployment and verification in the [pipeline](.github/workflows/build-images.yml). Document the architecture in the README and architecture guide. Omit operator runbooks.

## Run

```bash
cd src
npm install
npm run dev:backend    # Express API
npm run dev:frontend   # Vite dev server
npm run build          # build all workspaces
npm run typecheck      # typecheck all workspaces
```

## Operating rules

1. **Diagnose from the live env, not the code.** Check pod logs, `kubectl
   describe`, `kubectl get events`, and AWS resources first. Live cluster is the
   source of truth — never guess from code.
2. **Protect the live IF agent API.** Non-targeted `terraform apply` and all
   `terraform destroy` are hook-blocked. `kubectl cordon/drain` are blocked
   (single-node cluster). Destructive kubectl verbs are blocked only when they
   target the IF agent API (`if-agent-*` / `app=if-agent-api`) or a broad `all`/
   `--all` blast in `if-portals`; this portal's backend/frontend may be mutated
   freely. `terraform apply -target=...` needs explicit operator approval.
   Otherwise give the operator the command. Read-only kubectl and `terraform
   fmt/validate/plan` are fine.
3. **Never delete AWS resources.** Give the operator the command.
4. **No git writes.** Give the operator the command.
5. **Code first; don't over-plan.** Start implementing. Plan part 1 → implement →
   plan part 2 → implement. No hours of planning before code.
6. **No comments in code.** Self-documenting code; default zero comments.
7. **Prefer modules over stuffing one file.** Split by concern.
8. **When stuck, hand off and move on.** More than ~4 "but wait"/"let me
   reconsider" cycles on one problem → write the stuck point to `HANDOFF.md`, move
   to the next task. Come back only when the queue is done.
9. **Stay in scope — no rabbit holes.** Unrelated bug → `bug.md`. Unrelated
   instruction dropped mid-task → `todo.md`.
10. **"Pivot" means full pivot.** Drop current requirements, do the new ones.

## Build bar

`npm run build` must pass before declaring work done.

## Live test athlete

The private Authentik account `acceptance-luna-20260915` maps to Person/Athlete
`person_be8959131fea4ca395a38e8f`. It has an `Automated Test Program` and four
completed synthetic sessions: `automated-test-week-1` through `automated-test-week-3`
and `manual-export-check-20261123`. They cover Nov 2–23, 2026 and include
planned exercises plus actual per-set loads/RPE.

With Node dependencies installed in `src`, Playwright Chromium available, and
Kubernetes access to namespace `powerlifting`, create a normal headless OIDC
session with:

```bash
node scripts/test-auth-session.mjs
```

It creates a ten-minute Authentik app password, logs in through the usual OIDC
flow, verifies the expected Person, saves `/tmp/nolift-test-session.json` with
owner-only permissions, then deletes the password. Set `PL_STORAGE_STATE` to
change that location. The saved browser state is a credential; keep it out of
the repository and recreate it when expired. If interrupted, the temporary
password expires in ten minutes. Authentik API tokens do not authenticate to
NoLift; use the OAuth2 Proxy session cookie and never fabricate internal
identity headers.

`node scripts/test-live-api.mjs` reuses that session for direct HTTP checks
without launching a browser. `node scripts/test-live-browser.mjs` launches
headless Chromium and checks the training sessions in the UI. Both verify the
test account first. `node scripts/test-seed-athlete.mjs` completes onboarding,
initializes a program if needed, and adds the three weekly synthetic sessions
if missing; it does not delete or reset data. These API and browser checks are
read-only. The export API assertions currently fail on the live deployment
because the prescription and weekly e1RM changes are missing.
