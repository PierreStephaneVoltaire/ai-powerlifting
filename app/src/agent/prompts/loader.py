




from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent

_ORCHESTRATOR_PROMPTS_DIR = PROMPTS_DIR.parent.parent / "orchestrator" / "prompts"

_SEARCH_DIRS = [d for d in (PROMPTS_DIR, _ORCHESTRATOR_PROMPTS_DIR) if d.exists()]

_jinja_env: Optional[Environment] = None

def _get_jinja_env() -> Environment:





    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader([str(d) for d in _SEARCH_DIRS]),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
    return _jinja_env

def load_prompt(name: str) -> str:














    for search_dir in _SEARCH_DIRS:
        if not name.endswith(('.md', '.txt', '.j2')):
            path = search_dir / f"{name}.md"
            if path.exists():
                return path.read_text(encoding='utf-8').strip()

        path = search_dir / name
        if path.exists():
            return path.read_text(encoding='utf-8').strip()

    raise FileNotFoundError(f"Prompt file not found: {name} (searched: {[str(d) for d in _SEARCH_DIRS]})")

def render_template(name: str, **kwargs) -> str:

















    env = _get_jinja_env()
    
    if not name.endswith('.j2'):
        name = f"{name}.j2"
    
    try:
        template = env.get_template(name)
        return template.render(**kwargs)
    except TemplateNotFound:
        logger.error(f"Template not found: {name} in {PROMPTS_DIR}")
        raise

def get_template(name: str) -> Template:













    env = _get_jinja_env()
    
    if not name.endswith('.j2'):
        name = f"{name}.j2"
    
    return env.get_template(name)
