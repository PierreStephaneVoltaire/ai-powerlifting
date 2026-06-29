# Fission Phase 4 — HPA Tuning Runbook

Status: implemented (code-side). Operator-run steps marked **OPERATOR-RUN** — the
agent does not execute them (repo rules: no k3s restart, no kubectl mutation, no
terraform apply, no git writes).

This runbook covers three things:

1. The kube-controller-manager downscale-stabilization flag (node-level k3s
   config — not Terraform-managed).
2. Confirmation that Fission owns the per-function HPAs (no separate
   `kubernetes_horizontal_pod_autoscaler` resources are declared).
3. The expanded warm-read set + a soak-test checklist the operator runs after
   the Fission functions are live.

Scale profiles are generated from
`utils/powerlifting-app/lambda/fission_layers.py::SCALE_PROFILE` into
`utils/powerlifting-app/terraform/fission-functions.tf` by
`utils/powerlifting-app/lambda/fission-deploy.py`. The class assignment lives in
`fission_layers.py::tool_class` (precedence: ai > warm > stats > det).

## Part 1 — kube-controller-manager downscale-stabilization flag

The `--horizontal-pod-autoscaler-downscale-stabilization=120s` flag is a
**kube-controller-manager** argument, NOT a Fission helm value and NOT a Fission
CRD field. On k3s the kube-controller-manager runs embedded in the k3s server
process; the flag is passed through k3s via the `kube-controller-manager-arg`
key.

The repo Terraform does NOT manage k3s node config. `grep` across `terraform/`
finds no `kube-controller-manager`, `kube-controller-manager-arg`, `rancher`,
`systemd`, or k3s `config.yaml` resource (the only `config.yaml` reference is a
Grafana Alloy config in `k8s-observability.tf`, unrelated). k3s is a node-level
install, so this flag is set on the node, not in Terraform.

Why it matters: Fission's `newdeploy` executor creates one HPA per Function. An
HPA whose scale-to-zero target is reached can flap (scale to 0, then a trailing
request immediately scales back to 1) without a stabilization window. The 120s
downscale-stabilization makes the controller-manager wait 120s after the last
observed high-load point before it honors a scale-down recommendation, which
bounds churn for every Fission HPA on the single-node cluster.

### **OPERATOR-RUN** — set the flag on the k3s node

Run this on the k3s server node (not from the agent). The agent provides the
command; the operator runs it.

1. Edit `/etc/rancher/k3s/config.yaml`. Add the arg under the
   `kube-controller-manager-arg` key. If the key does not exist, add it. If it
   already has entries, append to the list:

   ```yaml
   kube-controller-manager-arg:
     - "horizontal-pod-autoscaler-downscale-stabilization=120s"
   ```

   If `kube-controller-manager-arg` is already a list with other args, keep
   them and add the new line. Do not duplicate the flag if it is already present.

2. Restart k3s to apply:

   ```bash
   sudo systemctl restart k3s
   ```

3. Verify the flag is live on the kube-controller-manager (read-only):

   ```bash
   ps -ef | grep kube-controller-manager | grep -o 'horizontal-pod-autoscaler-downscale-stabilization=[0-9]*s'
   ```

   Expected: `horizontal-pod-autoscaler-downscale-stabilization=120s`.

   Alternatively, after restart:

   ```bash
   kubectl -n kube-system get pod -l component=kube-controller-manager -o jsonpath='{.items[0].spec.containers[0].command}'
   ```

   (k3s embeds the controller-manager; the flag appears in the process args.)

### Why this is not in Terraform

The repo's Terraform manages Kubernetes/AWS resources via the k3s kubeconfig
(`var.kubeconfig_path`, `var.kubernetes_context`), not the k3s server process or
its `/etc/rancher/k3s/config.yaml`. Adding a `null_resource` that SSH-ed into the
node to rewrite node config would violate the no-mutating-k8s/node rule and
would run outside `terraform plan` safety. The node config stays operator-owned.

## Part 2 — Fission owns the per-function HPAs

Fission's `newdeploy` executor creates one HPA per Function automatically. The
`TargetCPUPercent` and `MinScale`/`MaxScale` in each Function's
`InvokeStrategy.ExecutionStrategy` are the values Fission passes to that HPA.
No separate `kubernetes_horizontal_pod_autoscaler` Terraform resources are
declared in `fission-functions.tf` (or anywhere in the repo) — declaring one
would fight Fission's own controller, which reconciles the HPA from the
Function CRD.

The generated `fission-functions.tf` Functions each carry:

```yaml
InvokeStrategy:
  StrategyType: execution
  ExecutionStrategy:
    ExecutorType: newdeploy
    MinScale: <minReplicas>
    MaxScale: <maxReplicas>
    SpecializationTimeout: <seconds>
    TargetCPUPercent: <percent>
```

Fission's controller reads that and maintains the HPA. Editing
`SCALE_PROFILE` in `fission_layers.py` and re-running
`python3 fission-deploy.py` regenerates all of `fission-functions.tf` with the
updated per-class values; `terraform plan` then diffs the
`kubectl_manifest` resources, and `terraform apply` (operator-run) applies the
Function CRD changes, which Fission reconciles down to the HPAs.

### Per-class scale profiles (SCALE_PROFILE)

| Class | minReplicas | maxReplicas | targetCPU | SpecializationTimeout | Tools |
|-------|-------------|-------------|-----------|-----------------------|-------|
| ai    | 0           | 1           | 70        | 120                   | 15 deployed AI tools |
| warm  | 1           | 2           | 70        | 60                    | 10 read-only high-traffic reads |
| stats | 0           | 2           | 80        | 120                   | 5 stats/analytics tools |
| det   | 0           | 3           | 70        | 90                    | 65 remaining deterministic |

Generated counts (from `python3 fission-deploy.py --dry-run`): 95 deployable
tools, 15 ai, 10 warm, 5 stats, 65 det.

### Spot-check verification (fission-functions.tf)

These were confirmed in the regenerated `fission-functions.tf`:

- AI — `fatigue_profile_estimate`: MinScale 0, MaxScale 1, TargetCPUPercent 70,
  SpecializationTimeout 120.
- Warm — `health_get_program`: MinScale 1, MaxScale 2, TargetCPUPercent 70,
  SpecializationTimeout 60.
- Stats — `analyze_powerlifting_stats`: MinScale 0, MaxScale 2,
  TargetCPUPercent 80, SpecializationTimeout 120.
- Warm — `get_analysis_markdown`: MinScale 1, MaxScale 2, TargetCPUPercent 70,
  SpecializationTimeout 60.
- Det write — `health_add_exercise`: MinScale 0, MaxScale 3,
  TargetCPUPercent 70, SpecializationTimeout 90.

All 10 warm reads carry MinScale 1, MaxScale 2, TargetCPUPercent 70.

## Part 3 — Expanded warm-read set

`fission_layers.py::WARM_READS` previously listed 10 names, but only 4 resolved
to real deployable tool folders. Six were dead references to non-existent tools
(`glossary_list_terms`, `program_list`, `session_list`, `import_list`,
`federation_list`, `health_get_sessions`) that had no `handler.py` +
`resources.yaml` folder, so they never affected the generated scale profile
(effective warm count was 4, not 10).

The dead references were removed and the set was expanded to 10 verified
read-only tools that actually exist as deployable folders. Each was checked:
the handler does a GET/LIST (reads from DynamoDB via `get_item`/`query`/`scan`
or returns a static table), with no `put_item`/`update_item`/`delete_item` or
other mutation. None are in `AI_TOOLS`.

Final `WARM_READS` (10):

| Tool | Read type |
|------|-----------|
| `health_get_program` | single program GET (high-traffic portal read) |
| `health_get_session` | single session GET |
| `health_get_sessions_range` | date-range session LIST/GET |
| `health_get_current_maxes` | current maxes GET |
| `health_get_goals` | goals GET |
| `health_get_meta` | program meta GET |
| `health_get_phases` | phases GET |
| `template_list` | template LIST |
| `template_get` | full template GET |
| `get_analysis_markdown` | cached analysis markdown GET |

Rationale: these are the highest-traffic deterministic reads the portal UI and
the agent fire on load / navigation. `minReplicas=1` keeps one pod warm (~80MB
resident) so the UI path is snappy; the remaining 65 deterministic tools
(including all writes) scale to zero (`minReplicas=0`, `maxReplicas=3`).

Candidates that were reviewed and NOT added to warm: `health_get_competition`,
`health_get_diet_notes`, `health_get_federation_library`,
`health_get_supplements`, `import_list_pending`, `import_get_pending`,
`health_setup_status`, `export_program_history`, `export_program_markdown`,
`ipf_weight_classes` — all are read-only, but lower-traffic than the 10 above.
They remain in the `det` class (`minReplicas=0`). If any of these become a
UI hot-path, add them to `WARM_READS` and regenerate.

After editing `WARM_READS`, the tf was regenerated with:

```bash
cd utils/powerlifting-app/lambda && python3 fission-deploy.py
```

`terraform fmt -check -recursive` and `terraform validate` (init with
`-backend=false`) are green in `utils/powerlifting-app/terraform/`.

## Part 4 — Soak-test checklist (OPERATOR-RUN)

Run after the Fission functions are deployed and the
downscale-stabilization flag (Part 1) is live. All kubectl commands below are
read-only except where noted; the invocations themselves are HTTP calls to the
Fission router.

1. Confirm the downscale-stabilization flag is applied (Part 1, step 3).

2. Confirm the warm-read pods are already at 1 (they never scale to zero):

   ```bash
   kubectl -n if-portals get pods -l functionName=pl-fn-health_get_program
   kubectl -n if-portals get pods -l functionName=pl-fn-template_list
   ```

   Expected: 1 pod running for each warm read at all times.

3. Invoke one AI tool (scales 0->1, scales back to 0 after stabilization):

   ```bash
   kubectl -n if-portals exec deploy/if-powerlifting-backend -- \
     curl -sS -X POST http://router.fission/fatigue_profile_estimate \
       -H 'X-Internal-Token: <token>' -H 'Content-Type: application/json' \
       -d '{"args": {}}' | head -c 200
   ```

   Then watch it scale to 1, then back to 0:

   ```bash
   kubectl -n if-portals get pods -l functionName=pl-fn-fatigue_profile_estimate -w
   ```

   Expect: 1 pod appears on invoke; after idle + 120s stabilization it returns
   to 0.

4. Invoke one warm read (stays at 1, may scale to 2 under load):

   ```bash
   kubectl -n if-portals exec deploy/if-powerlifting-backend -- \
     curl -sS -X POST http://router.fission/health_get_program \
       -H 'X-Internal-Token: <token>' -H 'Content-Type: application/json' \
       -d '{"args": {}}' | head -c 200
   ```

   ```bash
   kubectl -n if-portals get pods -l functionName=pl-fn-health_get_program
   ```

   Expect: 1 pod (already warm); never 0.

5. Invoke one det write (scales 0->1, scales back to 0):

   ```bash
   kubectl -n if-portals exec deploy/if-powerlifting-backend -- \
     curl -sS -X POST http://router.fission/health_add_exercise \
       -H 'X-Internal-Token: <token>' -H 'Content-Type: application/json' \
       -d '{"args": <minimal valid args for a throwaway test program>}' | head -c 200
   ```

   Use `HEALTH_PROGRAM_PK=test`, never `operator`, for any write (per the
   test-data rule).

   ```bash
   kubectl -n if-portals get pods -l functionName=pl-fn-health_add_exercise -w
   ```

   Expect: 1 pod appears on invoke; after idle + 120s stabilization it returns
   to 0.

6. Idle 5 minutes with no invokes, then re-check all three:

   ```bash
   kubectl -n if-portals get pods -l functionName=pl-fn-fatigue_profile_estimate
   kubectl -n if-portals get pods -l functionName=pl-fn-health_get_program
   kubectl -n if-portals get pods -l functionName=pl-fn-health_add_exercise
   ```

   Expected after 5 min idle (the 120s stabilization window has elapsed):
   - `pl-fn-fatigue_profile_estimate`: 0 pods (scaled to zero).
   - `pl-fn-health_get_program`: 1 pod (warm — never scales to zero).
   - `pl-fn-health_add_exercise`: 0 pods (scaled to zero).

7. Confirm the downscale did not thrash. During the idle window, watch for
   repeated scale 0->1->0 cycles on the non-warm functions:

   ```bash
   kubectl -n if-portals get events --field-selector reason=Scheduled \
     --sort-by=.lastTimestamp | tail -40
   ```

   With the 120s stabilization flag, a non-warm function should scale to 0 once
   and stay at 0 through the idle window (no immediate re-scale). If it flaps,
   the flag is not applied — recheck Part 1 step 3.

8. Cold-start rehydrate timing (optional, post-soak): after the AI and det
   functions are at 0, invoke each once and time the first response. Expected:
   deterministic < 5s cold start; AI < 10s (OpenRouter stream latency dominates).