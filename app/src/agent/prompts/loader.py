"""Prompt template loader for externalized prompts.

Provides utilities to load static prompts (.md) and render Jinja2 templates (.j2)
from the src/agent/prompts/ directory, with fallback to src/orchestrator/prompts/.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

logger = logging.getLogger(__name__)

# Primary directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent

# Fallback directory for orchestrator-specific prompts (analyzer_*.j2, synthesizer.j2, etc.)
_ORCHESTRATOR_PROMPTS_DIR = PROMPTS_DIR.parent.parent / "orchestrator" / "prompts"

# Search order: agent/prompts first, orchestrator/prompts second
_SEARCH_DIRS = [d for d in (PROMPTS_DIR, _ORCHESTRATOR_PROMPTS_DIR) if d.exists()]

# Jinja2 environment for .j2 templates
_jinja_env: Optional[Environment] = None


def _get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment.
    
    Returns:
        Configured Jinja2 environment
    """
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader([str(d) for d in _SEARCH_DIRS]),
            autoescape=False,  # Don't auto-escape HTML
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
    return _jinja_env


def load_prompt(name: str) -> str:
    """Load a static prompt file.
    
    Loads .md or .txt files that don't require template rendering.
    Searches agent/prompts/ first, then orchestrator/prompts/.
    
    Args:
        name: Filename (with or without extension), e.g., "reflection.md"
        
    Returns:
        Content of the prompt file
        
    Raises:
        FileNotFoundError: If the prompt file doesn't exist in any search dir
    """
    for search_dir in _SEARCH_DIRS:
        # Try with and without extension
        if not name.endswith(('.md', '.txt', '.j2')):
            path = search_dir / f"{name}.md"
            if path.exists():
                return path.read_text(encoding='utf-8').strip()

        path = search_dir / name
        if path.exists():
            return path.read_text(encoding='utf-8').strip()

    raise FileNotFoundError(f"Prompt file not found: {name} (searched: {[str(d) for d in _SEARCH_DIRS]})")


def render_template(name: str, **kwargs) -> str:
    """Render a Jinja2 template with the given variables.
    
    Loads and renders .j2 template files with the provided context.
    
    Args:
        name: Template filename (with or without .j2 extension)
        **kwargs: Template variables to pass to Jinja2
        
    Returns:
        Rendered template string
        
    Raises:
        TemplateNotFound: If the template file doesn't exist
        
    Example:
        >>> prompt = render_template("opinion_formation.j2", topic="AI", user_position="pro")
    """
    env = _get_jinja_env()
    
    # Ensure .j2 extension
    if not name.endswith('.j2'):
        name = f"{name}.j2"
    
    try:
        template = env.get_template(name)
        return template.render(**kwargs)
    except TemplateNotFound:
        logger.error(f"Template not found: {name} in {PROMPTS_DIR}")
        raise


def get_template(name: str) -> Template:
    """Get a Jinja2 template object for later rendering.
    
    Useful when you need to render the same template multiple times.
    
    Args:
        name: Template filename (with or without .j2 extension)
        
    Returns:
        Jinja2 Template object
        
    Raises:
        TemplateNotFound: If the template file doesn't exist
    """
    env = _get_jinja_env()
    
    # Ensure .j2 extension
    if not name.endswith('.j2'):
        name = f"{name}.j2"
    
    return env.get_template(name)
