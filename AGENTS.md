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
- `powerlifting-app/terraform/k8s/{core,perms,network,app}` → the Powerlifting Kubernetes resources, one state each, applied by the in-cluster runner (`kubernetes-apply` job). See `terraform/k8s/README.md`.
- `powerlifting-app/terraform/coach/` → its own state for the Coach Kubernetes resources only (PVC, Deployments, Services), applied locally because CI cannot reach the cluster. Coach ECR repositories live in `powerlifting-app/terraform/` with the other AWS resources. See `src/services/coach/README.md`.

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
