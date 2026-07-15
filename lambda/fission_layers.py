"""Layer-to-source/pip contract used by `fission-deploy.py` to assemble each
function's source archive. Tool classification (ai/warm/stats/det) and scale
profiles are not in this file — they live in the main repo's
`terraform/k8s-fission-powerlifting.tf`, which is the single source of truth
for the Fission Function CRDs.
"""

import os

LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
LAYERS_DIR = os.path.join(LAMBDA_ROOT, "layers")

LAYER_MODULE_DIRS = {
    "pl_program": os.path.join(LAYERS_DIR, "pl-program", "python"),
    "pl_sessions": os.path.join(LAYERS_DIR, "pl-sessions", "python"),
    "pl_glossary": os.path.join(LAYERS_DIR, "pl-glossary", "python"),
    "pl_templates": os.path.join(LAYERS_DIR, "pl-templates", "python"),
    "pl_analysis_cache": os.path.join(LAYERS_DIR, "pl-analysis-cache", "python"),
    "pl_ai": os.path.join(LAYERS_DIR, "pl-ai", "content"),
    "pl_boto3": None,
}

LAYER_PIP_REQS = {
    "pl_boto3": ["boto3==1.42.83", "botocore==1.42.83", "s3transfer==0.16.0"],
    "pl_ai": ["httpx", "jinja2"],
    "pl_program": [],
    "pl_sessions": [],
    "pl_glossary": ["rapidfuzz==3.10.1"],
    "pl_templates": [],
    "pl_analysis_cache": [],
}

EXTRA_TOOL_REQS = {
    "analyze_progression": ["scipy"],
    "analyze_rpe_drift": ["scipy"],
}


def layer_modules(layer):
    d = LAYER_MODULE_DIRS.get(layer)
    if not d or not os.path.isdir(d):
        return []
    out = []
    for root, _dirs, files in os.walk(d):
        if "__pycache__" in root:
            continue
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, d)
            out.append((full, rel))
    return out


def _read_requirements_file(path):
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                yield line


def requirements_for(tool_id, layers):
    reqs = []
    for layer in layers:
        reqs.extend(LAYER_PIP_REQS.get(layer, []))
    reqs.extend(EXTRA_TOOL_REQS.get(tool_id, []))
    tool_root = os.path.join(LAMBDA_ROOT, tool_id)
    reqs.extend(_read_requirements_file(os.path.join(tool_root, "requirements.txt")))
    handlers_dir = os.path.join(tool_root, "handlers")
    if os.path.isdir(handlers_dir):
        for handler_name in sorted(os.listdir(handlers_dir)):
            reqs.extend(_read_requirements_file(os.path.join(handlers_dir, handler_name, "requirements.txt")))
    seen = set()
    out = []
    for r in reqs:
        key = r.split("==")[0].split(">=")[0].split("<=")[0].lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
