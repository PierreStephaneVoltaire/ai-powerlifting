# Handoff: ADR 0011 Part A review

Date: 2026-11-25. Scope: the uncommitted Codex implementation of Part A on branch `deployment`. Nothing is applied yet; the `argocd` namespace does not exist.

## Verdict

Good enough to move to Part B, after the fixes below and the operator inputs.

## Verified (read-only)

- `terraform validate` passes for `k8s/argocd`, `k8s/app`, `k8s/network`, `k8s/core`, `coach` and the AWS root. `terraform fmt -check` is clean.
- `kustomize build` succeeds for `deploy/argocd/app`, `coach` and `network` (159, 12 and 7 objects).
- **Live comparison.** Each Git object was created with a server-side dry run under a temporary name, and its spec compared with the live object. Every difference is a field Terraform injects:
  - ECR image
  - `nolift:private:` values
  - AWS workload env
  - Coach node selector
  - route hostnames
  - `BUILD_ID`
  - the oauth2-proxy cookie, covered by the handoff patch

  The HCL-to-YAML conversion has no gaps.
- **Plans.** `terraform plan -lock=false` for app, network and Coach plans 127, 6 and 10 deletions.
  - All are pure deletes of Deployment, Service, ServiceAccount or `kubectl_manifest`.
  - Each matches a rendered Git object that has a live UID, so the release gate in `argocd_handoff.py` will pass.
  - The only updates are:
    - the oauth2-proxy Secret (it gains the cookie key)
    - the gateway Helm release (it also watches `argocd`; the controller restarts once)
- **Versions.**
  - Chart argo-cd 10.20.0 (Argo CD v3.6.3) and chart argocd-image-updater 1.5.0 exist.
  - Image `v1.5.1` exists on quay.
  - The Argo CLI checksum matches the release.
  - Rendered images come only from quay and public ECR.
- **CRDs.** The leftover CRDs carry Helm ownership for releases `argocd` and `argocd-image-updater` in namespace `argocd`, and have 0 instances. The installs adopt them.
- **Private values.** No added file contains an account ID, hostname, LAN address or new domain.

## Fixes applied

1. **The oauth2-proxy promotion would fail.**
   - At the handoff, Argo applies the cookie env without a value. The literal value therefore stays owned by Terraform's `HashiCorp` field manager.
   - When the cookie patch is dropped, Argo applies `valueFrom`. The API then rejects it with `valueFrom: may not be specified when value is not empty` (reproduced with a server-side dry run).
   - Fix: on the first run after the handoff, `scripts/deploy_argocd.sh` replaces that env entry with the Secret reference, then renders without the handoff patch. The proxy rolls once and keeps the same cookie key.
2. **Tests are out of the deploy path.** `deploy_argocd.sh` ran `terraform test` and the Python unittests on every deploy. Both calls are removed.
3. **The Playwright login step is out of `kubernetes-apply`.** See the next section.

## Codex additions that do not follow the instructions

- **New tests:** `scripts/test_argocd_handoff.py`, `scripts/test_argocd_images.py` and `terraform/k8s/argocd/tests/manifests.tftest.hcl`.
  - Breaks: no new tests by default.
  - Now: the pipeline no longer runs them. Delete them with the command at the end.
- **Live login check on every Kubernetes deploy.** The step:
  - ran `test-auth-session.mjs` and `test-live-api.mjs`
  - minted an Authentik app password through `kubectl exec` into authentik-worker
  - ran `npm ci` of `src/`
  - installed Chromium with system packages on the in-cluster runner

  Breaks:
  - no live acceptance runs unless asked
  - the runner shares the node disk
  - the goal is faster deploys

  Now: removed. Run the check once by hand after the handoff. The `PL_APP_ORIGIN` override in both scripts is harmless and stays.
- **`litellm_image` passed as `nolift:private:litellm_image`.**
  - Breaks: markers are for private values only.
  - Now: left as is. Later, put the literal image in `deploy/argocd/app/litellm.yaml` and remove `var.litellm_image` from the argocd stack.
- **Network policy toggles stay in tfvars.** These are `network_policy_ingress_workloads`, `network_policy_egress_workloads` and `waypoint_network_policy_enabled`. At render, Terraform deletes about 30 Git policies with `$patch: delete`.
  - Breaks: Git holds the manifests, and Terraform injects only private values.
  - Now: left, because it keeps today's staged rollout. Later, move the enabled set into Git and remove the toggles.
- **PR 1 and PR 2 are merged into one.** The handoff, the journal ConfigMap, `rollback_argocd.py` and the `argocd_rollback_revision` dispatch input stay in the pipeline permanently.
  - Breaks: ADR A4 says PR 2 deletes the handoff script.
  - Now: left. Delete them after promotion.
- **An `ImageUpdater` for `network` with `useAnnotations: true`.** It exists only to satisfy the CRD when there are no images.
  - Now: harmless. It would be better to skip apps that have no ECR repositories.
- **460 lines of Kustomize `replacements` in `deploy/argocd/app/kustomization.yaml`.**
  - These are needed. They copy the pinned image into `BUILD_ID` (cache invalidation), and they remove the `:latest` that Image Updater adds before the digest.
  - Every new Deployment needs its own two blocks.

**Pre-existing, carried over unchanged (not Codex):** `valkey/valkey:7.2.5` and `cloudflare/cloudflared:2024.10.1` are Docker Hub images. Changing them during the handoff would restart those pods, so replace them after promotion.

## Known gaps (not fixed)

- **Removing a field from Git does not remove it live.**
  - Adopted objects keep the `HashiCorp` field manager, and `ClientSideApplyMigration=false`, so fields set by both Terraform and Argo stay co-owned.
  - Adding or changing a field works. That is all Part B needs (tolerations and affinity).
  - Fix after promotion: remove the `HashiCorp` entries from `metadata.managedFields` on the adopted objects. As an alternative, turn on migration with the annotation `argocd.argoproj.io/client-side-apply-migration-manager: HashiCorp`.
- **A new master commit during a run makes the wait time out.** The sync wait requires `status.sync.revision == $GITHUB_SHA`. `timeout.reconciliation` is `0s`, so the refresh resolves the newer head, and the wait never matches.
- **Code pushes do not deploy until auto sync is on.** Between the first run and promotion, Image Updater runs with 0 replicas and `deploy-frontend-only` is removed.

## Operator inputs before merging

- `main` environment variable `ARGOCD_DOMAIN`: a new hostname in the portal zone.
- `K8S_TFVARS` must contain `argocd_domain` and `argocd_admins` (Authentik usernames). `core` has no default for `argocd_admins`.
- Leave `argocd_auto_sync = false`. The first run forces manual sync anyway.

## Run order after the merge

1. **Run 1** (the merge to master). It:
   - installs Argo CD, plus Image Updater with 0 replicas
   - seeds digests from the live Deployments
   - checks that the dry run equals live
   - syncs
   - checks that UIDs and restart counts did not change
   - runs `terraform state rm` on the 143 adopted addresses
   - applies the retained stacks (the oauth2-proxy Secret gains the cookie key)
   - syncs the `argocd` route
2. **Run 2** (any change under `terraform/k8s/**` or `deploy/argocd/**`). oauth2-proxy moves to the Secret and to `$(APP_DOMAIN)`, and rolls once.
3. **Promotion.** Set `argocd_auto_sync = true` in `K8S_TFVARS` and trigger a run. This turns on auto sync and gives Image Updater 1 replica. From then on, code pushes deploy only through ECR digests. Runs 2 and 3 can be the same run.
4. **Manual checks:**
   - Log in to Argo CD through Authentik.
   - Run `node scripts/test-auth-session.mjs && node scripts/test-live-api.mjs`.
   - Push one service and check that only its Deployment rolls.

## After promotion (ADR PR 2 cleanup)

Delete:

- `scripts/argocd_handoff.sh`, `scripts/argocd_handoff.py` and `scripts/rollback_argocd.py`
- the rollback dispatch input
- the cookie handoff patch and `argocd_cookie_migrated`
- the journal checks in `deploy_argocd.sh`

Delete the Codex tests:

```
rm scripts/test_argocd_handoff.py scripts/test_argocd_images.py terraform/k8s/argocd/tests/manifests.tftest.hcl
```

## Part B readiness

Nothing in Part A blocks Part B:

- The B4 DaemonSet tolerations live in `core` and `mesh`, which Terraform still owns.
- The PR 5 opt-in tolerations go into `deploy/argocd/app/*.yaml` as plain fields.
