import argparse
import os
import zipfile
import yaml

import fission_layers as fl

LAMBDA_ROOT = fl.LAMBDA_ROOT
REPO_ROOT = os.path.normpath(os.path.join(LAMBDA_ROOT, "..", "..", ".."))
TERRAFORM_DIR = os.path.join(REPO_ROOT, "terraform")
BUILD_DIR = os.path.join(TERRAFORM_DIR, "fission-build")
OUTPUT_TF = os.path.join(TERRAFORM_DIR, "fission-functions.tf")
FUNCTION_NAMESPACE = "if-portals"
ENV_NAMESPACE = "fission"
ENV_NAME = "pl-fission-tools"
RUNTIME_IMAGE = "ghcr.io/fission/python-env"
BUILDER_IMAGE = "ghcr.io/fission/python-builder"
SECRETS_NAME = "pl-fission-secrets"
AUTHORIZER_FN = "pl-authorizer"
REGISTRY_TOOL = "tool_registry"
ENTRY_FILE = os.path.join(LAMBDA_ROOT, "fission_entry.py")

COMMON_ENV = [
    ("IF_AWS_REGION", "ca-central-1"),
    ("IF_HEALTH_TABLE_NAME", "if-health"),
    ("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
    ("IF_SESSIONS_TABLE_NAME", "if-sessions"),
    ("IF_ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"),
    ("HEALTH_PROGRAM_PK", "operator"),
    ("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
]

AI_ENV = [
    ("ANALYSIS_MODEL", "anthropic/claude-sonnet-4.6"),
    ("ESTIMATE_MODEL", "anthropic/claude-sonnet-4.6"),
    ("IMPORT_FAST_MODEL", "anthropic/claude-haiku-4.5"),
    ("GLOSSARY_TEXT_MODEL", "google/gemini-3.1-flash-lite"),
]

STATS_ENV = [
    ("POWERLIFTING_S3_BUCKET", "${var.powerlifting_s3_bucket}"),
]


def _tf_safe(name):
    return name.replace("-", "_").replace(".", "_")


def _read_resources(folder):
    with open(os.path.join(folder, "resources.yaml")) as f:
        return yaml.safe_load(f) or {}


def _build_archive(tool_id, folder, layers):
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, tool_id + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ENTRY_FILE, "fission_entry.py")
        for root, _dirs, files in os.walk(folder):
            if "__pycache__" in root:
                continue
            for fn in files:
                if fn.endswith(".pyc") or fn.endswith(".zip"):
                    continue
                if not fn.endswith((".py", ".json", ".yaml", ".j2")):
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


def _env_block(tool_id, res):
    envs = list(COMMON_ENV)
    if fl.tool_class(tool_id) == "ai":
        envs.extend(AI_ENV)
    if res.get("s3_read"):
        envs.extend(STATS_ENV)
    envs.append(("IF_TOOL_NAME", tool_id))
    lines = []
    for name, val in envs:
        lines.append(f"            - name: {name}")
        lines.append(f"              value: \"{val}\"")
    lines.append(f"          envFrom:")
    lines.append(f"            - secretRef:")
    lines.append(f"                name: {SECRETS_NAME}")
    return "\n".join(lines)


def _scale_block(tool_id):
    s = fl.SCALE_PROFILE[fl.tool_class(tool_id)]
    return f"""        InvokeStrategy:
          StrategyType: execution
          ExecutionStrategy:
            ExecutorType: newdeploy
            MinScale: {s["minReplicas"]}
            MaxScale: {s["maxReplicas"]}
            SpecializationTimeout: {s["timeout"]}
            TargetCPUPercent: {s["targetCPU"]}"""


def _package_yaml(tool_id, archive_path):
    return f"""apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-{tool_id}
  namespace: {FUNCTION_NAMESPACE}
spec:
  environment:
    name: {ENV_NAME}
    namespace: {ENV_NAMESPACE}
  buildcmd: /usr/local/bin/build
  source:
    type: literal
    literal: {os.path.basename(archive_path)}"""


def _tool_block(tool_id, res):
    desc = (res.get("description") or tool_id).replace('"', '\\"')
    schema = res.get("input_schema") or {"type": "object", "properties": {}}
    schema_json = yaml.safe_dump(schema, default_flow_style=False, sort_keys=False)
    indented = "\n".join("      " + l for l in schema_json.rstrip().split("\n"))
    return f"""  tool:
    name: {tool_id}
    description: "{desc}"
    inputSchema: |
{indented}"""


def _function_yaml(tool_id, res):
    mem = res.get("memory", 256)
    timeout = res.get("timeout", 900)
    return f"""apiVersion: fission.io/v1
kind: Function
metadata:
  name: pl-fn-{tool_id}
  namespace: {FUNCTION_NAMESPACE}
spec:
  environment:
    name: {ENV_NAME}
    namespace: {ENV_NAMESPACE}
  package:
    packageref:
      name: pl-pkg-{tool_id}
      namespace: {FUNCTION_NAMESPACE}
  functionTimeout: {timeout}
  concurrency: 500
{_scale_block(tool_id)}
{_tool_block(tool_id, res)}
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-{tool_id}
        image: {RUNTIME_IMAGE}
        imagePullPolicy: IfNotPresent
{_env_block(tool_id, res)}
        resources:
          requests:
            cpu: 100m
            memory: {max(128, mem // 2)}Mi
          limits:
            cpu: 1000m
            memory: {mem}Mi
    volumes: []"""


def _trigger_yaml(tool_id):
    if tool_id == REGISTRY_TOOL:
        return f"""apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-{tool_id}
  namespace: {FUNCTION_NAMESPACE}
spec:
  functionref:
    type: name
    name: pl-fn-{tool_id}
  methods:
    - GET
  relativeurl: /openapi.json"""
    return f"""apiVersion: fission.io/v1
kind: HTTPTrigger
metadata:
  name: pl-ht-{tool_id}
  namespace: {FUNCTION_NAMESPACE}
spec:
  functionref:
    type: name
    name: pl-fn-{tool_id}
  methods:
    - POST
  relativeurl: /{tool_id}
  prefn:
    - name: {AUTHORIZER_FN}
      namespace: {FUNCTION_NAMESPACE}"""


def _archive_resource(tool_id, archive_path):
    return f'''data "archive_file" "pl_{_tf_safe(tool_id)}" {{
  type        = "zip"
  output_path = "{archive_path}"
  source_dir  = "{os.path.dirname(archive_path)}"
}}

'''


def _manifest_resource(tool_id, kind, yaml_body):
    kind_map = {"package": "pl_pkg", "function": "pl_fn", "trigger": "pl_ht"}
    res = kind_map[kind] + "_" + _tf_safe(tool_id)
    return f'''resource "kubectl_manifest" "{res}" {{
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
{yaml_body}
YAML
}}

'''


def _authorizer_block():
    folder = os.path.join(LAMBDA_ROOT, "pl_authorizer")
    archive = os.path.join(BUILD_DIR, "pl_authorizer.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ENTRY_FILE, "fission_entry.py")
        for fn in os.listdir(folder):
            if fn.endswith(".py") and fn != "__init__.py":
                zf.write(os.path.join(folder, fn), os.path.join("pl_authorizer", fn))
        zf.writestr("requirements.txt", "")
    pkg = f"""apiVersion: fission.io/v1
kind: Package
metadata:
  name: pl-pkg-pl-authorizer
  namespace: {FUNCTION_NAMESPACE}
spec:
  environment:
    name: {ENV_NAME}
    namespace: {ENV_NAMESPACE}
  source:
    type: literal
    literal: pl_authorizer.zip"""
    fn = f"""apiVersion: fission.io/v1
kind: Function
metadata:
  name: {AUTHORIZER_FN}
  namespace: {FUNCTION_NAMESPACE}
spec:
  environment:
    name: {ENV_NAME}
    namespace: {ENV_NAMESPACE}
  package:
    packageref:
      name: pl-pkg-pl-authorizer
      namespace: {FUNCTION_NAMESPACE}
  functionTimeout: 5
  InvokeStrategy:
    StrategyType: execution
    ExecutionStrategy:
      ExecutorType: newdeploy
      MinScale: 0
      MaxScale: 1
      SpecializationTimeout: 30
      TargetCPUPercent: 70
  podspec:
    serviceAccountName: default
    containers:
      - name: pl-authorizer
        image: {RUNTIME_IMAGE}
        imagePullPolicy: IfNotPresent
        env:
          - name: IF_TOOL_NAME
            value: "pl_authorizer"
          - name: INTERNAL_API_TOKEN
            valueFrom:
              secretKeyRef:
                name: {SECRETS_NAME}
                key: INTERNAL_API_TOKEN
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 200m
            memory: 128Mi
    volumes: []"""
    out = _manifest_resource("pl_authorizer", "package", pkg)
    out += _manifest_resource("pl_authorizer", "function", fn)
    return out


def generate_tf():
    os.makedirs(BUILD_DIR, exist_ok=True)
    header = "resource \"kubectl_manifest\" \"pl_fission_env\" {\n  server_side_apply = true\n  force_conflicts   = true\n  yaml_body         = <<-YAML\n"
    header += f"""apiVersion: fission.io/v1
kind: Environment
metadata:
  name: {ENV_NAME}
  namespace: {ENV_NAMESPACE}
spec:
  version: 3
  keeparchive: false
  runtime:
    image: {RUNTIME_IMAGE}
  builder:
    image: {BUILDER_IMAGE}
  terminationGracePeriod: 120
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 1000m
      memory: 512Mi
YAML
}}

"""
    body = ""
    counts = {"tool": 0, "pkg": 0, "fn": 0, "ht": 0}
    for tool_id in fl.deployable_tools():
        folder = os.path.join(LAMBDA_ROOT, tool_id)
        res = _read_resources(folder)
        layers = res.get("layers") or []
        archive = _build_archive(tool_id, folder, layers)
        pkg_yaml = _package_yaml(tool_id, archive)
        fn_yaml = _function_yaml(tool_id, res)
        ht_yaml = _trigger_yaml(tool_id)
        body += _manifest_resource(tool_id, "package", pkg_yaml)
        body += _manifest_resource(tool_id, "function", fn_yaml)
        body += _manifest_resource(tool_id, "trigger", ht_yaml)
        counts["tool"] += 1
        counts["pkg"] += 1
        counts["fn"] += 1
        counts["ht"] += 1
    body += _authorizer_block()
    counts["pkg"] += 1
    counts["fn"] += 1
    return header + body, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        counts = {"tool": 0, "pkg": 0, "fn": 0, "ht": 0}
        for tool_id in fl.deployable_tools():
            counts["tool"] += 1
            counts["pkg"] += 1
            counts["fn"] += 1
            counts["ht"] += 1
        counts["pkg"] += 1
        counts["fn"] += 1
        import json
        print(json.dumps({
            "deployable_tools": len(fl.deployable_tools()),
            "tools": counts["tool"],
            "packages": counts["pkg"],
            "functions": counts["fn"],
            "triggers": counts["ht"],
            "ai": sum(1 for t in fl.deployable_tools() if fl.tool_class(t) == "ai"),
            "warm": sum(1 for t in fl.deployable_tools() if fl.tool_class(t) == "warm"),
            "stats": sum(1 for t in fl.deployable_tools() if fl.tool_class(t) == "stats"),
            "det": sum(1 for t in fl.deployable_tools() if fl.tool_class(t) == "det"),
        }, indent=2))
        return
    tf, counts = generate_tf()
    with open(OUTPUT_TF, "w") as f:
        f.write(tf)
    print(f"wrote {OUTPUT_TF} (tools={counts['tool']}, pkgs={counts['pkg']}, fns={counts['fn']}, hts={counts['ht']})")


if __name__ == "__main__":
    main()
