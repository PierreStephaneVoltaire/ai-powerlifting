#!/usr/bin/env bash
set -euo pipefail
umask 077
work=$(mktemp -d "${RUNNER_TEMP:?}/nolift-argocd.XXXXXX")
trap 'rm -rf "$work"' EXIT
k8s_vars="$RUNNER_TEMP/k8s.tfvars"
terraform -chdir=terraform/k8s/argocd init -input=false -backend-config="bucket=$TF_STATE_BUCKET" \
  -backend-config="key=powerlifting-app/k8s/argocd.tfstate" -backend-config="region=$AWS_REGION" -backend-config="encrypt=true" -backend-config="use_lockfile=true"
kubectl config set-context --current --namespace=argocd > /dev/null
for stack in network app coach; do
  if [[ $stack == coach ]]; then directory=terraform/coach; else directory="terraform/k8s/$stack"; fi
  terraform -chdir="$directory" output -json manifest_inputs > "$work/$stack.inputs"
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
terraform -chdir=terraform/k8s/argocd apply -input=false -compact-warnings -auto-approve \
  -var-file="$k8s_vars" -var-file="$work/manifest.tfvars.json" > /dev/null
unset TF_VAR_argocd_client_secret
resume_updates
trap 'rm -rf "$work"' EXIT
for app in app coach network; do
  name="nolift-$app"
  kubectl -n argocd annotate application "$name" argocd.argoproj.io/refresh=normal --overwrite
  kubectl -n argocd wait application/"$name" --for="jsonpath={.status.sync.revision}=$GITHUB_SHA" --timeout=10m
  argocd app wait "$name" --core --sync --health --timeout 900
done
for app in app coach network; do
  kubectl -n argocd get application "nolift-$app" -o json | jq -e --arg sha "$GITHUB_SHA" \
    '.status.sync.revision == $sha and .status.sync.status == "Synced" and .status.health.status == "Healthy"' > /dev/null
done
