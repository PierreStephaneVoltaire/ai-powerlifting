#!/usr/bin/env bash
set -euo pipefail
umask 077
work=$(mktemp -d "${RUNNER_TEMP:?}/nolift-argocd.XXXXXX")
trap 'rm -rf "$work"' EXIT
k8s_vars="$RUNNER_TEMP/k8s.tfvars"
coach_vars="$RUNNER_TEMP/coach.tfvars"
stacks=(network app coach)

stack_dir() {
  if [[ $1 == coach ]]; then echo terraform/coach; else echo "terraform/k8s/$1"; fi
}

vars_for() {
  if [[ $1 == coach ]]; then echo "$coach_vars"; else echo "$k8s_vars"; fi
}

plan_retained() {
  local stack
  for stack in "${stacks[@]}"; do
    terraform -chdir="$(stack_dir "$stack")" plan -input=false -compact-warnings -lock-timeout=2m \
      -var-file="$(vars_for "$stack")" -out="$work/$stack.plan" > /dev/null
    terraform -chdir="$(stack_dir "$stack")" show -json "$work/$stack.plan" > "$work/$stack.json"
  done
}

apply_retained() {
  local stack
  for stack in "${stacks[@]}"; do
    terraform -chdir="$(stack_dir "$stack")" apply -input=false "$work/$stack.plan" > /dev/null
  done
}

for stack in core perms network mesh app argocd coach; do
  key="powerlifting-app/k8s/$stack.tfstate"
  if [[ $stack == coach ]]; then key=powerlifting-app/coach/terraform.tfstate; fi
  terraform -chdir="$(stack_dir "$stack")" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" \
    -backend-config="key=$key" -backend-config="region=$AWS_REGION" -backend-config="encrypt=true" -backend-config="use_lockfile=true"
done

if [[ -n ${ROLLBACK_REVISION:-} ]]; then
  python3 scripts/rollback_argocd.py "$ROLLBACK_REVISION" "$work"
  exit
fi
if [[ $(kubectl -n argocd get configmap nolift-terraform-handoff --ignore-not-found -o jsonpath='{.metadata.annotations.nolift\.io/rolled-back}') == true ]]; then
  echo "Terraform ownership was restored by the rollback workflow. Restore the matching Terraform revision on master." >&2
  exit 1
fi
for stack in core perms mesh; do
  terraform -chdir="$(stack_dir "$stack")" apply -input=false -auto-approve -compact-warnings -var-file="$k8s_vars" > /dev/null
done
kubectl config set-context --current --namespace=argocd > /dev/null
handoff=$(kubectl -n argocd get configmap nolift-terraform-handoff --ignore-not-found -o jsonpath='{.metadata.annotations.nolift\.io/complete}')
plan_retained
if [[ $handoff == true ]]; then
  kubectl -n argocd get configmap nolift-terraform-handoff -o json > "$work/journal"
  for stack in "${stacks[@]}"; do
    jq -e --slurpfile journal "$work/journal" --arg stack "$stack" '
      ($journal[0].data[$stack] | fromjson | map(.address)) as $adopted |
      all(.resource_changes[]? | select(.change.actions | index("delete")); .address as $addr | $adopted | index($addr) == null)
    ' "$work/$stack.json" > /dev/null || { echo "Terraform would delete an adopted $stack object" >&2; exit 1; }
  done
  apply_retained
fi
for stack in "${stacks[@]}"; do
  if [[ $handoff == true ]]; then
    terraform -chdir="$(stack_dir "$stack")" output -json manifest_inputs > "$work/$stack.inputs"
  else
    jq -e '.planned_values.outputs.manifest_inputs.value // error("Missing manifest inputs")' "$work/$stack.json" > "$work/$stack.inputs"
  fi
done

jq -n --slurpfile app "$work/app.inputs" --slurpfile coach "$work/coach.inputs" --slurpfile network "$work/network.inputs" \
  '{app_inputs: $app[0], coach_inputs: $coach[0], network_inputs: $network[0]}' \
  > "$work/manifest.tfvars.json"
TF_VAR_argocd_client_secret=$(terraform -chdir=terraform/k8s/core output -raw argocd_client_secret)
export TF_VAR_argocd_client_secret
updater=deployment/argocd-image-updater-controller
resume_updates() {
  if [[ -n $(kubectl -n argocd get application nolift-app -o jsonpath='{.spec.syncPolicy.automated}') ]]; then
    kubectl -n argocd scale "$updater" --replicas=1
  fi
}
if [[ $(kubectl -n argocd get "$updater" --ignore-not-found -o jsonpath='{.spec.replicas}') == 1 ]]; then
  kubectl -n argocd scale "$updater" --replicas=0
  trap 'rm -rf "$work"; resume_updates' EXIT
  kubectl -n argocd wait --for=delete pod -l app.kubernetes.io/name=argocd-image-updater --timeout=2m
fi
cookie_migrated=$(kubectl -n argocd get configmap nolift-terraform-handoff --ignore-not-found -o jsonpath='{.metadata.annotations.nolift\.io/promoted}')
if [[ $cookie_migrated != true ]]; then
  cookie_migrated=$(kubectl -n powerlifting get deployment/oauth2-proxy -o json | jq 'any(.spec.template.spec.containers[].env[]?; .name == "OAUTH2_PROXY_COOKIE_SECRET" and .valueFrom.secretKeyRef.name == "oauth2-proxy-secrets")')
fi
if [[ $handoff == true && $cookie_migrated != true ]]; then
  cookie_index=$(kubectl -n powerlifting get deployment/oauth2-proxy -o json | jq -e '.spec.template.spec.containers[0].env | map(.name) | index("OAUTH2_PROXY_COOKIE_SECRET")')
  kubectl -n powerlifting patch deployment/oauth2-proxy --type=json --field-manager=argocd-controller \
    -p "$(jq -nc --argjson i "$cookie_index" '[{op: "replace", path: "/spec/template/spec/containers/0/env/\($i)", value: {name: "OAUTH2_PROXY_COOKIE_SECRET", valueFrom: {secretKeyRef: {name: "oauth2-proxy-secrets", key: "OAUTH2_PROXY_COOKIE_SECRET"}}}}]')"
  cookie_migrated=true
fi
phase=()
if [[ $handoff != true ]]; then phase=(-var=argocd_auto_sync=false); fi
terraform -chdir=terraform/k8s/argocd apply -input=false -compact-warnings -auto-approve \
  -var-file="$k8s_vars" -var-file="$work/manifest.tfvars.json" -var="argocd_cookie_migrated=$cookie_migrated" "${phase[@]}" > /dev/null
unset TF_VAR_argocd_client_secret
resume_updates
trap 'rm -rf "$work"' EXIT
if [[ $handoff == true && -n $(kubectl -n argocd get application nolift-app -o jsonpath='{.spec.syncPolicy.automated}') ]]; then
  kubectl -n argocd annotate configmap/nolift-terraform-handoff nolift.io/promoted=true --overwrite
fi

if [[ $handoff != true ]]; then
  bash scripts/argocd_handoff.sh "$work"
  plan_retained
  for stack in "${stacks[@]}"; do
    jq -e 'all(.resource_changes[]?; .mode != "managed" or (.change.actions | index("delete") == null))' "$work/$stack.json" > /dev/null || {
      echo "A deletion remains in $stack after the handoff" >&2
      exit 1
    }
  done
  apply_retained
  argocd app sync nolift-network --core --revision "$GITHUB_SHA" --timeout 600
fi

if [[ $handoff == true && -z $(kubectl -n argocd get application nolift-app -o jsonpath='{.spec.syncPolicy.automated}') ]]; then
  for app in app coach network; do
    argocd app manifests "nolift-$app" --core --source git --revision "$GITHUB_SHA" > "$work/$app.yaml"
  done
  python3 scripts/argocd_handoff.py render "$work"
fi
for app in app coach network; do
  name="nolift-$app"
  kubectl -n argocd annotate application "$name" argocd.argoproj.io/refresh=normal --overwrite
  if [[ $handoff == true && $(kubectl -n argocd get application "$name" -o jsonpath='{.spec.syncPolicy.automated}') == "" ]]; then
    argocd app sync "$name" --core --revision "$GITHUB_SHA" --timeout 600
  fi
  kubectl -n argocd wait application/"$name" --for="jsonpath={.status.sync.revision}=$GITHUB_SHA" --timeout=10m
  argocd app wait "$name" --core --sync --health --timeout 900
done
for app in app coach network; do
  argocd app manifests "nolift-$app" --core --source live > "$work/$app.yaml"
  kubectl -n argocd get application "nolift-$app" -o json | jq -e --arg sha "$GITHUB_SHA" \
    '.status.sync.revision == $sha and .status.sync.status == "Synced" and .status.health.status == "Healthy"' > /dev/null
done
python3 scripts/argocd_handoff.py render "$work"
if [[ $handoff != true ]]; then
  kubectl -n argocd annotate configmap nolift-terraform-handoff nolift.io/complete=true --overwrite
fi
