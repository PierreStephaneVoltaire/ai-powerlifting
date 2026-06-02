



from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

def _interpolate_env_vars(value: Any) -> Any:









    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]
    return value

def load_yaml(path: Path) -> Dict[str, Any]:












    if not path.exists():
        raise FileNotFoundError(f"YAML config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    return _interpolate_env_vars(data)
