#!/bin/bash
set -euo pipefail

CATEGORY="${MCP_CATEGORY:?MCP_CATEGORY env var is required}"
PORT="${MCP_PORT:-8000}"
HOST="${MCP_HOST:-0.0.0.0}"
TOOLS_ROOT="${IF_TOOLS_ROOT:-/app/tools}"
REQUIREMENTS_FILE="${TOOLS_ROOT}/${CATEGORY}/requirements.txt"

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "[mcp-server] requirements file not found: ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

echo "[mcp-server] category=${CATEGORY} host=${HOST} port=${PORT}"
echo "[mcp-server] installing ${REQUIREMENTS_FILE}"

PIP_ARGS=(
    install
    --no-cache-dir
    --disable-pip-version-check
    --root-user-action=ignore
    -r "${REQUIREMENTS_FILE}"
)

if grep -qE 'download\.pytorch\.org' "${REQUIREMENTS_FILE}"; then
    PIP_ARGS+=(--extra-index-url https://download.pytorch.org/whl/cpu)
fi

python3 -m pip "${PIP_ARGS[@]}"

echo "[mcp-server] starting mcp_server.py ${CATEGORY} on ${HOST}:${PORT}/mcp"
exec python3 \
    "${TOOLS_ROOT}/mcp_server.py" \
    "${CATEGORY}" \
    --transport http \
    --host "${HOST}" \
    --port "${PORT}" \
    --mount-path /mcp \
    "$@"
