"""Build per-tool source archives for the Fission `container` executor.

The powerlifting subrepo is responsible for assembling each function's source
zip (handler + per-tool deps + shared layer modules + a pinned requirements.txt
for the image build). The Packer template in `docker/powerlifting-fn.pkr.hcl`
unzips the archive, pip-installs `requirements.txt`, and pushes the image to
ECR. The main repo's `terraform/k8s-fission-powerlifting.tf` is the single
source of truth for the Fission Function / HTTPTrigger CRDs and the scale
fields — this script does not generate any Terraform.
"""

import argparse
import json
import os
import zipfile

import yaml

import fission_layers as fl

LAMBDA_ROOT = fl.LAMBDA_ROOT
REPO_ROOT = os.path.normpath(os.path.join(LAMBDA_ROOT, ".."))
BUILD_DIR = os.path.join(REPO_ROOT, "terraform", "fission-build")
ENTRY_FILE = os.path.join(LAMBDA_ROOT, "fission_entry.py")
ENTRY_ZIP_NAME = "main.py"
ARCHIVE_EXTS = (".py", ".json", ".yaml", ".j2")
SKIP_TOOLS = {"layers", "pl_authorizer"}


def _read_resources(folder):
    with open(os.path.join(folder, "resources.yaml")) as f:
        return yaml.safe_load(f) or {}


def _build_archive(tool_id, folder, layers):
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, tool_id + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ENTRY_FILE, ENTRY_ZIP_NAME)
        zf.writestr("tool_id.txt", tool_id + "\n")
        for root, _dirs, files in os.walk(folder):
            if "__pycache__" in root:
                continue
            for fn in files:
                if fn.endswith(".pyc") or fn.endswith(".zip"):
                    continue
                if not fn.endswith(ARCHIVE_EXTS):
                    continue
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, folder)
                zf.write(full, os.path.join(tool_id, arc))
        for layer in layers:
            for src, rel in fl.layer_modules(layer):
                zf.write(src, rel)
        reqs = fl.requirements_for(tool_id, layers)
        if reqs:
            zf.writestr("requirements.txt", "\n".join(reqs) + "\n")
    return out


def _deployable_tools():
    return sorted(
        t for t in os.listdir(LAMBDA_ROOT)
        if t not in SKIP_TOOLS
        and os.path.isfile(os.path.join(LAMBDA_ROOT, t, "resources.yaml"))
        and os.path.isfile(os.path.join(LAMBDA_ROOT, t, "handler.py"))
    )


def build_all():
    os.makedirs(BUILD_DIR, exist_ok=True)
    count = 0
    for tool_id in _deployable_tools():
        folder = os.path.join(LAMBDA_ROOT, tool_id)
        res = _read_resources(folder)
        layers = res.get("layers") or []
        _build_archive(tool_id, folder, layers)
        count += 1
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        ts = _deployable_tools()
        print(json.dumps({"deployable_tools": len(ts)}, indent=2))
        return
    count = build_all()
    print(f"built {count} archives in {BUILD_DIR}")


if __name__ == "__main__":
    main()
