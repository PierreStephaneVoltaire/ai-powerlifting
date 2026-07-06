#!/usr/bin/env bash
# Build the pl-templates Lambda layer zip.
#
# Produces pl-templates.zip with the layout Lambda expects:
#   python/<modules...>
#
# Pure-python layer: the store module is copied verbatim with NO pip install.
# boto3/botocore are provided by the pl-boto3 layer attached alongside.
#
# Usage:
#   bash utils/powerlifting-app/lambda/layers/pl-templates/build.sh
set -euo pipefail

LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
STAGE="${LAYER_DIR}/.stage"
ZIP_NAME="pl-templates.zip"

rm -rf "${STAGE}"
mkdir -p "${STAGE}/python"

# Copy the pure-python store modules into the staging python/ dir.
cp -R "${LAYER_DIR}/python/." "${STAGE}/python/"

# Strip pycache to keep the layer clean.
find "${STAGE}" -type d -name '__pycache__' -prune -exec rm -rf {} +

(
  cd "${STAGE}"
  zip -r "${LAYER_DIR}/${ZIP_NAME}" .
)

rm -rf "${STAGE}"
echo "Built: ${LAYER_DIR}/${ZIP_NAME}"