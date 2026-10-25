#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
region="${AWS_REGION:-ca-central-1}"
registry="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${region}.amazonaws.com"
tag="${IMAGE_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}"

cd "${root}/docker"
for target in "${@:-agent discord}"; do
  for name in $target; do
    case "$name" in
      agent | discord) template="powerlifting-coach-${name}" ;;
      *) echo "unknown target: $name (use agent or discord)" >&2; exit 1 ;;
    esac
    packer init "${template}.pkr.hcl"
    packer build -color=false -var "image_repository=${registry}/if-${template}" -var "image_tag=${tag}" "${template}.pkr.hcl"
  done
done
