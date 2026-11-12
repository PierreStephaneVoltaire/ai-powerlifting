
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent

_jinja_env: Optional[Environment] = None

def _get_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(PROMPTS_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
    return _jinja_env

def load_system_prompt(name: str) -> str:
    """Load a static system prompt template (no variables).

    Args:
        name: Template filename without extension, e.g. "correlation_system"

    Returns:
        Prompt string with leading/trailing whitespace stripped.
    """
    path = PROMPTS_DIR / f"{name}.j2"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()

def render_prompt(name: str, **kwargs) -> str:
    """Render a Jinja2 template with the given variables.

    Args:
        name: Template filename without .j2 extension, e.g. "correlation_user"
        **kwargs: Template variables.

    Returns:
        Rendered string.
    """
    env = _get_env()
    template_name = f"{name}.j2" if not name.endswith(".j2") else name
    try:
        tmpl = env.get_template(template_name)
        return tmpl.render(**kwargs)
    except TemplateNotFound:
        logger.error("Template not found: %s in %s", template_name, PROMPTS_DIR)
        raise
