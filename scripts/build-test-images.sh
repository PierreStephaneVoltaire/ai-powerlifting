#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AWS_REGION="${AWS_REGION:-ca-central-1}"
ECR_REPOSITORY_PREFIX="${ECR_REPOSITORY_PREFIX:-if}"
NAMESPACE="${NAMESPACE:-if-portals-test}"
IMAGE_TAG="${IMAGE_TAG:-test}"
FRONTEND_API_URL="${TEST_FRONTEND_API_URL:-http://localhost:3005/api}"
TEST_MODEL_ID="${TEST_MODEL_ID:-deepseek/deepseek-v4-flash}"

# Allow building only specific images
# Usage: --only frontend  or  --only api,backend,frontend
BUILD_ONLY="${BUILD_ONLY:-}"
if [[ "${1:-}" == "--only" && -n "${2:-}" ]]; then
  BUILD_ONLY="$2"
  shift 2
fi

should_build() {
  local component="$1"
  if [[ -z "$BUILD_ONLY" ]]; then
    return 0
  fi
  IFS=',' read -ra COMPONENTS <<< "$BUILD_ONLY"
  for c in "${COMPONENTS[@]}"; do
    if [[ "$c" == "$component" ]]; then
      return 0
    fi
  done
  return 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

print_status() {
  echo
  echo "== Kubernetes status =="
  kubectl -n "$NAMESPACE" get deployments,services,pods -o wide || true

  echo
  echo "== Recent logs =="
  for deployment in if-agent-api powerlifting-app-backend powerlifting-app-frontend; do
    echo
    echo "-- $deployment --"
    kubectl -n "$NAMESPACE" logs "deployment/$deployment" --all-containers=true --tail=120 || true
  done
}

refresh_test_model_config() {
  local tmpdir
  tmpdir="$(mktemp -d)"
  printf "%s\n" "$TEST_MODEL_ID" > "$tmpdir/model_ids.txt"
  cat > "$tmpdir/model_selection_rules.md" <<EOF
# Test Model Selection Rules

This private test namespace intentionally exposes only cheap test models.

- The planner must choose \`${TEST_MODEL_ID}\` for every route in \`${NAMESPACE}\`.
- Do not choose production-quality, expensive, online, or provider-specific fallback models in this namespace.
- If a prompt asks for powerlifting, technical, or research work, still use \`${TEST_MODEL_ID}\` because \`model_ids.txt\` is the hard allowlist for tests.
EOF

  kubectl -n "$NAMESPACE" create configmap if-agent-api-model-allowlist \
    --from-file="$tmpdir/model_ids.txt" \
    --from-file="$tmpdir/model_selection_rules.md" \
    --dry-run=client -o yaml \
    | kubectl apply -f -
  rm -rf "$tmpdir"
}

trap 'code=$?; echo "Test image deploy failed with exit code $code" >&2; print_status; exit "$code"' ERR

require_cmd aws
require_cmd docker
require_cmd kubectl
require_cmd packer

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

API_REPO="${REGISTRY}/${ECR_REPOSITORY_PREFIX}-agent-api"
BACKEND_REPO="${REGISTRY}/${ECR_REPOSITORY_PREFIX}-powerlifting-app-backend"
FRONTEND_REPO="${REGISTRY}/${ECR_REPOSITORY_PREFIX}-powerlifting-app-frontend"

API_IMAGE="${API_REPO}:${IMAGE_TAG}"
BACKEND_IMAGE="${BACKEND_REPO}:${IMAGE_TAG}"
FRONTEND_IMAGE="${FRONTEND_REPO}:${IMAGE_TAG}"

echo "Building test images for namespace ${NAMESPACE}"
echo "  API:      ${API_IMAGE}"
echo "  Backend:  ${BACKEND_IMAGE}"
echo "  Frontend: ${FRONTEND_IMAGE}"
echo "  Frontend API URL: ${FRONTEND_API_URL}"
echo "  Test model: ${TEST_MODEL_ID}"

aws ecr-public get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin public.ecr.aws
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

cd "$ROOT_DIR/docker"

if should_build api; then
  packer init build.pkr.hcl
  packer build \
    -var "image_repository=${API_REPO}" \
    -var "image_tag=${IMAGE_TAG}" \
    -var "tag_latest=false" \
    build.pkr.hcl
else
  echo "Skipping API image build"
fi

if should_build backend; then
  packer init portals-backend.pkr.hcl
  packer build \
    -var "image_repository=${BACKEND_REPO}" \
    -var "image_tag=${IMAGE_TAG}" \
    -var "tag_latest=false" \
    -var "portal_name=powerlifting-app" \
    -var "portal_port=3005" \
    portals-backend.pkr.hcl
else
  echo "Skipping backend image build"
fi

if should_build frontend; then
  packer init portals-frontend.pkr.hcl
  packer build \
    -var "image_repository=${FRONTEND_REPO}" \
    -var "image_tag=${IMAGE_TAG}" \
    -var "tag_latest=false" \
    -var "portal_name=powerlifting-app" \
    -var "api_url=${FRONTEND_API_URL}" \
    portals-frontend.pkr.hcl
else
  echo "Skipping frontend image build"
fi

if should_build api; then
  refresh_test_model_config
  kubectl -n "$NAMESPACE" set image deployment/if-agent-api "api=${API_IMAGE}"
  kubectl -n "$NAMESPACE" rollout restart deployment/if-agent-api
  kubectl -n "$NAMESPACE" rollout status deployment/if-agent-api --timeout=300s
fi

if should_build backend; then
  kubectl -n "$NAMESPACE" set image deployment/powerlifting-app-backend "backend=${BACKEND_IMAGE}"
  kubectl -n "$NAMESPACE" rollout restart deployment/powerlifting-app-backend
  kubectl -n "$NAMESPACE" rollout status deployment/powerlifting-app-backend --timeout=300s
fi

if should_build frontend; then
  kubectl -n "$NAMESPACE" set image deployment/powerlifting-app-frontend "frontend=${FRONTEND_IMAGE}"
  kubectl -n "$NAMESPACE" rollout restart deployment/powerlifting-app-frontend
  kubectl -n "$NAMESPACE" rollout status deployment/powerlifting-app-frontend --timeout=300s
fi

print_status

cat <<EOF

Port-forward commands for local validation:
  kubectl -n ${NAMESPACE} port-forward svc/if-agent-api 8001:8000
  kubectl -n ${NAMESPACE} port-forward svc/powerlifting-app-backend 3005:3005
  kubectl -n ${NAMESPACE} port-forward svc/powerlifting-app-frontend 3001:3001

Open the test frontend at:
  http://localhost:3001
EOF
