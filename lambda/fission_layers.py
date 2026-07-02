import os

LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
LAYERS_DIR = os.path.join(LAMBDA_ROOT, "layers")

LAYER_MODULE_DIRS = {
    "pl_program": os.path.join(LAYERS_DIR, "pl-program", "python"),
    "pl_sessions": os.path.join(LAYERS_DIR, "pl-sessions", "python"),
    "pl_glossary": os.path.join(LAYERS_DIR, "pl-glossary", "python"),
    "pl_templates": os.path.join(LAYERS_DIR, "pl-templates", "python"),
    "pl_imports": os.path.join(LAYERS_DIR, "pl-imports", "python"),
    "pl_federation": os.path.join(LAYERS_DIR, "pl-federation", "python"),
    "pl_analysis_cache": os.path.join(LAYERS_DIR, "pl-analysis-cache", "python"),
    "pl_budget": os.path.join(LAYERS_DIR, "pl-budget", "python"),
    "pl_goals": os.path.join(LAYERS_DIR, "pl-goals", "python"),
    "pl_per_user": os.path.join(LAYERS_DIR, "pl-per-user", "python"),
    "pl_federation_library": os.path.join(LAYERS_DIR, "pl-federation-library", "python"),
    "pl_master_copy": os.path.join(LAYERS_DIR, "pl-master-copy", "python"),
    "pl_ai": os.path.join(LAYERS_DIR, "pl-ai", "content"),
    "pl_rag": os.path.join(LAYERS_DIR, "pl-rag", "python"),
    "pl_boto3": None,
    "pl_pandas": None,
}

LAYER_PIP_REQS = {
    "pl_boto3": ["boto3==1.42.83", "botocore==1.42.83", "s3transfer==0.16.0"],
    "pl_pandas": ["pandas==2.2.3", "numpy==2.1.3"],
    "pl_ai": ["httpx", "jinja2"],
    "pl_rag": ["chromadb==0.4.24", "tika==2.6.0"],
    "pl_program": [],
    "pl_sessions": [],
    "pl_glossary": [],
    "pl_templates": [],
    "pl_imports": [],
    "pl_federation": [],
    "pl_analysis_cache": [],
    "pl_budget": [],
    "pl_goals": [],
    "pl_per_user": [],
    "pl_federation_library": [],
    "pl_master_copy": [],
}

EXTRA_TOOL_REQS = {
    "analyze_progression": ["scipy"],
    "analyze_rpe_drift": ["scipy"],
}

SKIP_TOOLS = {"layers", "pl_authorizer"}

AI_TOOLS = {
    "budget_advisor", "block_program_evaluation", "block_comparison_synthesis",
    "budget_priority_timeline", "correlation_analysis", "e1rm_backfill",
    "fatigue_profile_estimate", "glossary_estimate_e1rm", "glossary_estimate_fatigue",
    "glossary_generate_text", "glossary_resolve_term", "import_classify_file",
    "import_parse_file", "lift_profile_estimate_stimulus", "lift_profile_rewrite",
    "lift_profile_review", "muscle_group_estimate", "program_evaluation",
    "template_evaluate", "multi_block_comparison",
}

WARM_READS = {
    "health_get_program", "health_get_session", "health_get_sessions_range",
    "health_get_current_maxes", "health_get_goals", "health_get_meta",
    "health_get_phases", "template_list", "template_get",
    "get_analysis_markdown", "tool_registry",
}

STATS_TOOLS = {
    "analyze_powerlifting_stats", "powerlifting_filter_categories",
    "powerlifting_ranking_percentile", "analyze_progression", "analyze_rpe_drift",
}

SCALE_PROFILE = {
    "ai": {"minReplicas": 0, "maxReplicas": 1, "targetCPU": 70, "timeout": 120},
    "warm": {"minReplicas": 1, "maxReplicas": 2, "targetCPU": 70, "timeout": 60},
    "stats": {"minReplicas": 0, "maxReplicas": 2, "targetCPU": 80, "timeout": 120},
    "det": {"minReplicas": 0, "maxReplicas": 3, "targetCPU": 70, "timeout": 90},
}


def tool_class(tool_id):
    if tool_id in AI_TOOLS:
        return "ai"
    if tool_id in WARM_READS:
        return "warm"
    if tool_id in STATS_TOOLS:
        return "stats"
    return "det"


def is_deployable(tool_id):
    if tool_id in SKIP_TOOLS:
        return False
    folder = os.path.join(LAMBDA_ROOT, tool_id)
    return os.path.isfile(os.path.join(folder, "handler.py")) and os.path.isfile(os.path.join(folder, "resources.yaml"))


def deployable_tools():
    return sorted(t for t in os.listdir(LAMBDA_ROOT) if is_deployable(t))


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


def requirements_for(tool_id, layers):
    reqs = []
    for layer in layers:
        reqs.extend(LAYER_PIP_REQS.get(layer, []))
    reqs.extend(EXTRA_TOOL_REQS.get(tool_id, []))
    # Merge the tool's own requirements.txt (per-tool deps like scipy that are
    # not in any layer and not in EXTRA_TOOL_REQS). fission-deploy.py writes the
    # merged list into the archive's requirements.txt; without this the tool's
    # own requirements.txt is never copied into the archive (the build filter only
    # ships .py/.json/.yaml/.j2), so per-tool deps were silently dropped.
    tool_req_file = os.path.join(LAMBDA_ROOT, tool_id, "requirements.txt")
    if os.path.isfile(tool_req_file):
        with open(tool_req_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#"):
                    reqs.append(_line)
    seen = set()
    out = []
    for r in reqs:
        key = r.split("==")[0].split(">=")[0].split("<=")[0].lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
