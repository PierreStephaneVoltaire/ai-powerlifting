#!/bin/sh
set -eu

kubectl -n cattle-system wait --for=create plan/nolift-home-tailnet --timeout=5m
kubectl -n cattle-system wait --for=condition=Complete plan/nolift-home-tailnet --timeout=10m

control_plane=$(kubectl get nodes -l node-role.kubernetes.io/control-plane -o json)
if ! printf '%s\n' "$control_plane" |
  jq -e 'any(.items[].status.addresses[]; .type == "InternalIP" and (.address | test("^100\\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\.")))' >/dev/null; then
  echo 'Tailscale setup complete. On the home server, run: sudo systemctl restart k3s'
fi
