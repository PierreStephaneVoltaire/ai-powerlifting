#!/usr/bin/env bash
# Build the pl-boto3 Lambda layer zip.
#
# Produces pl-boto3.zip with the layout Lambda expects:
#   python/lib/python3.12/site-packages/<packages...>
#
# Usage:
#   bash utils/powerlifting-app/lambda/layers/pl-boto3/build.sh
#
# Requires: Python 3.12 and pip available as `python3` + `pip`.
set -euo pipefail

LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
STAGE="${LAYER_DIR}/.stage"
PYTHON_VERSION="python3.12"

rm -rf "${STAGE}"
mkdir -p "${STAGE}/${PYTHON_VERSION}/site-packages"

# Install pinned deps into the staging site-packages dir.
pip install \
  --platform manylinux2014_x86_64 \
  --target "${STAGE}/${PYTHON_VERSION}/site-packages" \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-deps \
  -r "${LAYER_DIR}/requirements.txt"

# boto3 pulls in botocore + s3transfer + their deps (jmespath, urllib3, python-dateutil, six).
# Install the full transitive set with deps so the layer is self-contained.
pip install \
  --platform manylinux2014_x86_64 \
  --target "${STAGE}/${PYTHON_VERSION}/site-packages" \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  -r "${LAYER_DIR}/requirements.txt"

# Strip pycache and tests to shrink the layer.
find "${STAGE}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${STAGE}" -type d -name 'tests' -prune -exec rm -rf {} +
find "${STAGE}" -type d -name 'botocore/data' -prune -exec rm -rf {} + 2>/dev/null || true

(
  cd "${STAGE}"
  zip -r "${LAYER_DIR}/pl-boto3.zip" .
)

rm -rf "${STAGE}"
echo "Built: ${LAYER_DIR}/pl-boto3.zip"