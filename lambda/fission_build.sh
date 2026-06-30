#!/bin/sh
set -eu
# Fission python-builder build script (spec.buildcmd = "./build.sh").
# Runs in the builder pod with SRC_PKG (unzipped source) and DEPLOY_PKG (output).
# pip installs requirements into the source tree (if requirements.txt exists),
# copies everything to the deploy dir, then makes it all world-readable. The
# chmod is required because the builder runs as root but the Fission fetcher
# sidecar that archives + uploads the deploy package runs as uid 65532 —
# without a+rX the fetcher gets "permission denied" reading the installed files
# and the build fails. The requirements.txt guard handles tools with no deps.
if [ -f "${SRC_PKG}/requirements.txt" ]; then
  # The Fission python-env runs Python 3.13, and onnxruntime (a chromadb
  # dependency for its default ONNX embedding model) has no Python 3.13 wheel.
  # Our health_rag_search tool uses sentence-transformers, not the ONNX model,
  # so we install chromadb with --no-deps and then install its other runtime
  # deps explicitly (skipping onnxruntime).
  if grep -q 'chromadb' "${SRC_PKG}/requirements.txt"; then
    # Phase 1: install chromadb itself without pulling its dependency tree.
    grep 'chromadb' "${SRC_PKG}/requirements.txt" | pip3 install --no-deps -t ${SRC_PKG} -r /dev/stdin
    # Phase 2: install chromadb's actual runtime deps (minus onnxruntime).
    pip3 install -t ${SRC_PKG} chroma-hnswlib posthog pyyaml fastapi uvicorn \
      tenacity 'pulsar-client==3.4.0' rank-bm25 mmh3 pydantic orjson \
      grpcio protobuf kubernetes 2>/dev/null || true
    # Phase 3: install any other (non-chromadb) requirements normally.
    grep -v 'chromadb' "${SRC_PKG}/requirements.txt" | pip3 install -t ${SRC_PKG} -r /dev/stdin 2>/dev/null || true
  else
    pip3 install -r ${SRC_PKG}/requirements.txt -t ${SRC_PKG}
  fi
fi
cp -r ${SRC_PKG}/. ${DEPLOY_PKG}/
chmod -R a+rX ${DEPLOY_PKG}