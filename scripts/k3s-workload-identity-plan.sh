#!/bin/sh
set -eu
[ "$#" -eq 2 ] || { printf '%s\n' 'Usage: k3s-workload-identity-plan.sh ISSUER RUN_ID' >&2; exit 1; }
issuer=$1
run_id=$2
case "$issuer" in https://[a-zA-Z0-9.-]* ) ;; *) exit 1 ;; esac
case "$issuer" in *[!a-zA-Z0-9./:-]*|*/) exit 1 ;; esac
case "$run_id" in ''|*[!a-zA-Z0-9.-]*) exit 1 ;; esac
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
discovery=$(kubectl get --raw /.well-known/openid-configuration)
current=$(printf '%s' "$discovery" | jq -er '.issuer')
jwks=$(printf '%s' "$discovery" | jq -er '.jwks_uri')
if [ "$current" = "$issuer" ] && [ "$jwks" = "$issuer/openid/v1/jwks" ]; then
  exit 0
fi
[ "$current" != "$issuer" ] || { printf '%s\n' 'Issuer matches but JWKS URI differs; refusing to guess the previous issuer' >&2; exit 1; }
nodes=$(kubectl get nodes -l node-role.kubernetes.io/control-plane -o json)
node=$(printf '%s' "$nodes" | jq -er 'if (.items | length) == 1 then .items[0].metadata.labels["kubernetes.io/hostname"] // error("missing node hostname label") else error("expected exactly one control-plane node") end')
jq -n --arg node "$node" --arg version "$run_id" --arg issuer "$issuer" --arg previous "$current" --rawfile script "$script_dir/k3s-workload-identity-host.sh" '{apiVersion:"upgrade.cattle.io/v1",kind:"Plan",metadata:{name:"nolift-workload-identity",namespace:"cattle-system"},spec:{concurrency:1,version:$version,nodeSelector:{matchLabels:{"kubernetes.io/hostname":$node}},serviceAccountName:"system-upgrade-controller",upgrade:{image:"alpine:3.21.3",command:["/bin/sh","-c"],args:[$script],envs:[{name:"ISSUER",value:$issuer},{name:"PREVIOUS_ISSUER",value:$previous}]}}}'
