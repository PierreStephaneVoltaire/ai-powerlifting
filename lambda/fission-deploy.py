import argparse
import os
import zipfile
import yaml

import fission_layers as fl

LAMBDA_ROOT = fl.LAMBDA_ROOT
REPO_ROOT = os.path.normpath(os.path.join(LAMBDA_ROOT, ".."))
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
ENTRY_ZIP_NAME = "main.py"  # Fission python-env imports 'main' module by default

COMMON_ENV = [
    ("IF_AWS_REGION", "ca-central-1"),
    ("IF_HEALTH_TABLE_NAME", "if-health"),
    ("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
    ("IF_SESSIONS_TABLE_NAME", "if-sessions"),
    ("IF_ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"),
    ("IF_USER_TABLE", "if-user"),
    ("VIDEOS_BUCKET", "powerlifting-session-videos"),
    ("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
    ("BUDGET_MEDIA_BUCKET", "powerlifting-budget-media"),
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


def _read_resources(folder):
    with open(os.path.join(folder, "resources.yaml")) as f:
        return yaml.safe_load(f) or {}


def _build_archive(tool_id, folder, layers):
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, tool_id + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ENTRY_FILE, ENTRY_ZIP_NAME)
        # Fission source-archive build script: the python-builder runs this
        # (spec.buildcmd = "./build.sh") and it pip-installs requirements.txt
        # into the deploy archive. Lives at archive root as build.sh.
        zf.write(os.path.join(LAMBDA_ROOT, "fission_build.sh"), "build.sh")
        # Bake the tool id into the archive so the entry can load the
        # correct handler module without relying on per-function env vars
        # (Fission newdeploy does not merge function.spec.podspec into the
        # runtime container, and the router drops the URL path).
        zf.writestr("tool_id.txt", tool_id + "\n")
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


def _manifest_resource(name_prefix, yaml_body):
    return f'resource "kubectl_manifest" "{name_prefix}" {{\n  server_side_apply = true\n  force_conflicts   = true\n  yaml_body         = <<-YAML\n{yaml_body}\nYAML\n}}\n\n'


def _build_authorizer():
    folder = os.path.join(LAMBDA_ROOT, "pl_authorizer")
    res = _read_resources(folder)
    resources = res["resources"]
    archive = os.path.join(BUILD_DIR, "pl_authorizer.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ENTRY_FILE, ENTRY_ZIP_NAME)
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
      MinScale: {res.get("min_replicas", 0)}
      MaxScale: {res.get("max_replicas", 1)}
      SpecializationTimeout: {res.get("idle_timeout_seconds", 30)}
      TargetCPUPercent: {res.get("target_cpu", 70)}
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
            cpu: {resources["requests"]["cpu"]}
            memory: {resources["requests"]["memory"]}
          limits:
            cpu: {resources["limits"]["cpu"]}
            memory: {resources["limits"]["memory"]}
    volumes: []"""
    return _manifest_resource("pl_authorizer_pkg", pkg) + _manifest_resource("pl_authorizer_fn", fn)


HEADER = '''resource "kubectl_manifest" "pl_fission_env" {
  server_side_apply = true
  force_conflicts   = true
  yaml_body         = <<-YAML
apiVersion: fission.io/v1
kind: Environment
metadata:
  name: pl-fission-tools
  namespace: fission
spec:
  version: 3
  keeparchive: false
  runtime:
    image: ghcr.io/fission/python-env
  builder:
    image: ghcr.io/fission/python-builder
  terminationGracePeriod: 120
YAML
}

'''

LOOPS = '''locals {
  pl_common_env = [
    { name = "IF_AWS_REGION", value = "ca-central-1" },
    { name = "IF_HEALTH_TABLE_NAME", value = "if-health" },
    { name = "IF_TEMPLATES_TABLE_NAME", value = "if-health-templates" },
    { name = "IF_SESSIONS_TABLE_NAME", value = "if-sessions" },
    { name = "IF_ANALYSIS_CACHE_TABLE_NAME", value = "if-powerlifting-analysis-cache" },
    { name = "IF_USER_TABLE", value = "if-user" },
    { name = "VIDEOS_BUCKET", value = "powerlifting-session-videos" },
    { name = "POWERLIFTING_BUDGET_TABLE", value = "if-powerlifting-budget" },
    { name = "BUDGET_MEDIA_BUCKET", value = "powerlifting-budget-media" },
    { name = "HEALTH_PROGRAM_PK", value = "operator" },
    { name = "LLM_BASE_URL", value = "https://openrouter.ai/api/v1" },
  ]

  pl_ai_env = [
    { name = "ANALYSIS_MODEL", value = "anthropic/claude-sonnet-4.6" },
    { name = "ESTIMATE_MODEL", value = "anthropic/claude-sonnet-4.6" },
    { name = "IMPORT_FAST_MODEL", value = "anthropic/claude-haiku-4.5" },
    { name = "GLOSSARY_TEXT_MODEL", value = "google/gemini-3.1-flash-lite" },
  ]

  pl_tools = {
__TOOLS__
  }
}

resource "kubectl_manifest" "pl_packages" {
  for_each = local.pl_tools

  server_side_apply = true
  force_conflicts   = true
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "Package"
    metadata = {
      name      = "pl-pkg-${each.key}"
      namespace = "if-portals"
    }
    spec = {
      environment = { name = "pl-fission-tools", namespace = "fission" }
      buildcmd     = "/usr/local/bin/build"
      source = { type = "literal", literal = each.value.archive }
    }
  })
}

resource "kubectl_manifest" "pl_functions" {
  for_each = local.pl_tools

  server_side_apply = true
  force_conflicts   = true
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "Function"
    metadata = {
      name      = "pl-fn-${each.key}"
      namespace = "if-portals"
    }
    spec = {
      environment = { name = "pl-fission-tools", namespace = "fission" }
      package = { packageref = { name = "pl-pkg-${each.key}", namespace = "if-portals" } }
      functionTimeout = each.value.timeout
      concurrency     = 500
      InvokeStrategy = {
        StrategyType = "execution"
        ExecutionStrategy = {
          ExecutorType          = "newdeploy"
          MinScale              = each.value.min_scale
          MaxScale              = each.value.max_scale
          SpecializationTimeout = each.value.spec_timeout
          TargetCPUPercent      = each.value.target_cpu
        }
      }
      podspec = {
        serviceAccountName = "default"
        containers = [
          {
            name            = "pl-${each.key}"
            image           = "ghcr.io/fission/python-env"
            imagePullPolicy = "IfNotPresent"
            env = concat(
              local.pl_common_env,
              [{ name = "IF_TOOL_NAME", value = each.key }],
              each.value.class == "ai" ? local.pl_ai_env : [],
              each.value.s3_read ? [{ name = "POWERLIFTING_S3_BUCKET", value = var.powerlifting_s3_bucket }] : [],
            )
            envFrom = [{ secretRef = { name = "pl-fission-secrets" } }]
            resources = each.value.resources
          },
        ]
        volumes = []
      }
    }
  })
}

resource "kubectl_manifest" "pl_triggers" {
  for_each = local.pl_tools

  server_side_apply = true
  force_conflicts   = true
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "HTTPTrigger"
    metadata = {
      name      = "pl-ht-${each.key}"
      namespace = "if-portals"
    }
    spec = {
      functionref = { type = "name", name = "pl-fn-${each.key}" }
      methods = each.value.is_registry ? ["GET"] : ["POST"]
      relativeurl = each.value.is_registry ? "/openapi.json" : "/${each.key}"
      prefn = each.value.is_registry ? [] : [{ name = "pl-authorizer", namespace = "if-portals" }]
    }
  })
}

'''


def _scale_for(tool_id, res):
    """Resolve scale values from resources.yaml, falling back to the class profile.

    resources.yaml fields (all optional):
      min_replicas: int           — Fission MinScale (defaults: pod_* → 1, else 0)
      max_replicas: int           — Fission MaxScale (class-based default)
      target_cpu: int             — Fission TargetCPUPercent (class-based default)
      idle_timeout_seconds: int   — Fission SpecializationTimeout, idle keepalive
                                    (class-based default)

    min_replicas has no class fallback because the user wants to choose per
    function which ones are always up; the class-based default for warm tools
    (MinScale=1) is now expressed explicitly in resources.yaml instead.
    """
    cls = fl.tool_class(tool_id)
    defaults = fl.SCALE_PROFILE[cls]
    pod_default_min = 1 if tool_id.startswith("pod_") else 0
    return {
        "min_scale": int(res.get("min_replicas", pod_default_min)),
        "max_scale": int(res.get("max_replicas", defaults["maxReplicas"])),
        "target_cpu": int(res.get("target_cpu", defaults["targetCPU"])),
        "spec_timeout": int(res.get("idle_timeout_seconds", defaults["timeout"])),
    }


def generate_tf():
    os.makedirs(BUILD_DIR, exist_ok=True)
    tools = {}
    for tool_id in fl.deployable_tools():
        folder = os.path.join(LAMBDA_ROOT, tool_id)
        res = _read_resources(folder)
        layers = res.get("layers") or []
        archive = _build_archive(tool_id, folder, layers)
        scale = _scale_for(tool_id, res)
        resources = res["resources"]
        tools[tool_id] = {
            "archive": os.path.basename(archive),
            "class": fl.tool_class(tool_id),
            "resources": resources,
            "timeout": res.get("timeout", 900),
            "s3_read": bool(res.get("s3_read")),
            "is_registry": tool_id == REGISTRY_TOOL,
            "min_scale": scale["min_scale"],
            "max_scale": scale["max_scale"],
            "spec_timeout": scale["spec_timeout"],
            "target_cpu": scale["target_cpu"],
        }

    tools_str = ""
    for tid in sorted(tools):
        t = tools[tid]
        r = t["resources"]
        tools_str += f'    "{tid}" = {{\n'
        tools_str += f'      archive       = "{t["archive"]}"\n'
        tools_str += f'      class          = "{t["class"]}"\n'
        tools_str += f'      resources      = {{\n'
        tools_str += f'        requests = {{\n'
        tools_str += f'          cpu    = "{r["requests"]["cpu"]}"\n'
        tools_str += f'          memory = "{r["requests"]["memory"]}"\n'
        tools_str += f'        }}\n'
        tools_str += f'        limits = {{\n'
        tools_str += f'          cpu    = "{r["limits"]["cpu"]}"\n'
        tools_str += f'          memory = "{r["limits"]["memory"]}"\n'
        tools_str += f'        }}\n'
        tools_str += f'      }}\n'
        tools_str += f'      timeout        = {t["timeout"]}\n'
        tools_str += f'      s3_read        = {str(t["s3_read"]).lower()}\n'
        tools_str += f'      is_registry    = {str(t["is_registry"]).lower()}\n'
        tools_str += f'      min_scale      = {t["min_scale"]}\n'
        tools_str += f'      max_scale      = {t["max_scale"]}\n'
        tools_str += f'      spec_timeout   = {t["spec_timeout"]}\n'
        tools_str += f'      target_cpu     = {t["target_cpu"]}\n'
        tools_str += '    }\n'

    loops = LOOPS.replace("__TOOLS__", tools_str)
    counts = {"tool": len(tools), "pkg": len(tools) + 1, "fn": len(tools) + 1, "ht": len(tools)}
    return HEADER + loops + _build_authorizer(), counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        import json
        ts = fl.deployable_tools()
        print(json.dumps({
            "deployable_tools": len(ts),
            "ai": sum(1 for t in ts if fl.tool_class(t) == "ai"),
            "warm": sum(1 for t in ts if fl.tool_class(t) == "warm"),
            "stats": sum(1 for t in ts if fl.tool_class(t) == "stats"),
            "det": sum(1 for t in ts if fl.tool_class(t) == "det"),
        }, indent=2))
        return
    os.makedirs(BUILD_DIR, exist_ok=True)
    count = 0
    for tool_id in fl.deployable_tools():
        folder = os.path.join(LAMBDA_ROOT, tool_id)
        res = _read_resources(folder)
        layers = res.get("layers") or []
        _build_archive(tool_id, folder, layers)
        count += 1
    _build_authorizer()
    print(f"built {count + 1} archives in {BUILD_DIR}")


if __name__ == "__main__":
    main()
