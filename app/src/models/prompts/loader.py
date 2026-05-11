"""Prompt loader for model routing templates."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

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


def render_prompt(name: str, **kwargs) -> str:
    env = _get_env()
    template_name = f"{name}.j2" if not name.endswith(".j2") else name
    try:
        return env.get_template(template_name).render(**kwargs)
    except TemplateNotFound:
        raise FileNotFoundError(f"Prompt template not found: {PROMPTS_DIR / template_name}")
