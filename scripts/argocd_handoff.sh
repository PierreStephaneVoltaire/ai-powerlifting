#!/usr/bin/env bash
set -euo pipefail
work=$1
apps=(app coach network)
render() {
  for app in "${apps[@]}"; do
    argocd app manifests "nolift-$app" --core --source git --revision "$GITHUB_SHA" > "$work/$app.yaml"
  done
}
render
python3 scripts/argocd_handoff.py seed "$work"
render
python3 scripts/argocd_handoff.py before "$work"
for app in "${apps[@]}"; do
  result=0
  argocd app diff "nolift-$app" --core --revision "$GITHUB_SHA" --exit-code --diff-exit-code 42 > /dev/null || result=$?
  if [[ $result != 0 && $result != 42 ]]; then exit "$result"; fi
done
for app in "${apps[@]}"; do
  resources=()
  if [[ $app == network ]]; then
    resources=(--resource '!gateway.networking.k8s.io:HTTPRoute:argocd')
  fi
  argocd app sync "nolift-$app" --core --revision "$GITHUB_SHA" --timeout 600 "${resources[@]}"
done
python3 scripts/argocd_handoff.py after "$work"
python3 scripts/argocd_handoff.py release "$work"
kubectl -n argocd get configmap nolift-terraform-handoff --ignore-not-found -o json > "$work/journal"
for app in "${apps[@]}"; do
  jq -ns --arg app "$app" --slurpfile old "$work/journal" --slurpfile new "$work/$app.imports" \
    '(($old[0].data[$app] // "[]") | fromjson) + $new[0] | unique_by(.address)' > "$work/$app.journal"
done
kubectl -n argocd create configmap nolift-terraform-handoff \
  --from-file=app="$work/app.journal" --from-file=coach="$work/coach.journal" --from-file=network="$work/network.journal" \
  --dry-run=client -o yaml | kubectl apply -f -
for stack in "${apps[@]}"; do
  dir="terraform/k8s/$stack"
  if [[ $stack == coach ]]; then dir=terraform/coach; fi
  mapfile -t addresses < "$work/$stack.addresses"
  if ((${#addresses[@]})); then
    terraform -chdir="$dir" state rm -lock-timeout=2m "${addresses[@]}"
  fi
done
