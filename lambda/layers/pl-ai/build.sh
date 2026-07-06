#!/usr/bin/env bash
set -euo pipefail

LAYER_DIR="$(cd "$(dirname "$0")" && pwd)"
STAGE="${LAYER_DIR}/.stage"
ZIP_NAME="pl-ai.zip"
PYTHON_VERSION="python3.12"
SITE="${STAGE}/${PYTHON_VERSION}/lib/${PYTHON_VERSION}/site-packages"
CONTENT_DIR="${LAYER_DIR}/content"

rm -rf "${STAGE}"
mkdir -p "${SITE}"
mkdir -p "${STAGE}/python/prompts"

pip install \\
  --platform manylinux2014_x86_64 \\
  --target "${SITE}" \\
  --implementation cp \\
  --python-version 3.12 \\
  --only-binary=:all: \\
  httpx jinja2

cp "${CONTENT_DIR}/ai_config.py" "${STAGE}/python/ai_config.py"
cp "${CONTENT_DIR}/prompts/loader.py" "${STAGE}/python/prompts/loader.py"
cp "${CONTENT_DIR}"/prompts/*.j2 "${STAGE}/python/prompts/"

find "${STAGE}" -type d -name '__pycache__' -prune -exec rm -rf {} +

(
  cd "${STAGE}"
  zip -r "${LAYER_DIR}/${ZIP_NAME}" .
)

rm -rf "${STAGE}"
echo "Built: ${LAYER_DIR}/${ZIP_NAME}"
