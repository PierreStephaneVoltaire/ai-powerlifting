"""Specialist subagent registry and configuration.

Loads specialist definitions from YAML files in the specialists/ directory.
Each specialist is a subfolder containing specialist.yaml and agent.j2.

Specialists are auto-discovered by scanning subdirectories at module load.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from config import SPECIALIST_PRESET, SPECIALIST_MAX_TURNS, AGENTIC_MAX_ITERATIONS, SPECIALISTS_PATH
from agent.prompts.loader import render_template
from agent.prompts.yaml_loader import load_yaml

logger = logging.getLogger(__name__)

SPECIALISTS_DIR = Path(SPECIALISTS_PATH)


@dataclass
class SpecialistConfig:
    """Configuration for a specialist subagent.

    Attributes:
        slug: URL-safe identifier (derived from folder name)
        description: Human-readable description for tool UI
        template: Jinja2 template path (derived: specialists/{slug}/agent.j2)
        tools: List of tool names this specialist can use
        mcp_servers: List of MCP server slugs to attach
        directive_types: Types of directives to inject
        preset: OpenRouter preset to use
        max_turns: Maximum turns before timeout (non-agentic path)
        agentic: Legacy metadata indicating a specialist may need iterative execution
        max_iterations: Legacy iteration budget metadata
        skills: List of AgentSkills names this specialist uses (loaded at spawn time)
    """
    slug: str
    description: str
    template: str
    tools: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    directive_types: List[str] = field(default_factory=lambda: ["core"])
    preset: str = SPECIALIST_PRESET
    max_turns: int = SPECIALIST_MAX_TURNS
    agentic: bool = False
    max_iterations: int = AGENTIC_MAX_ITERATIONS
    skills: List[str] = field(default_factory=list)
    context_builder: Optional[str] = None


def _load_specialists() -> Dict[str, SpecialistConfig]:
    """Scan specialist subdirectories and load from specialist.yaml.

    Returns:
        Dict mapping slug to SpecialistConfig
    """
    registry: Dict[str, SpecialistConfig] = {}

    if not SPECIALISTS_DIR.is_dir():
        logger.error(f"Specialists directory not found: {SPECIALISTS_DIR}")
        return registry

    for subdir in sorted(SPECIALISTS_DIR.iterdir()):
        if not subdir.is_dir():
            continue

        config_path = subdir / "specialist.yaml"
        template_path = subdir / "agent.j2"

        if not config_path.exists():
            continue
        if not template_path.exists():
            logger.warning(f"Specialist {subdir.name} missing agent.j2, skipping")
            continue

        try:
            data = load_yaml(config_path)
        except Exception as e:
            logger.error(f"Failed to load specialist {subdir.name}: {e}")
            continue

        slug = subdir.name
        registry[slug] = SpecialistConfig(
            slug=slug,
            description=data.get("description", slug),
            template=f"specialists/{slug}/agent.j2",
            tools=data.get("tools", []),
            mcp_servers=data.get("mcp_servers", []),
            directive_types=data.get("directive_types", ["core"]),
            preset=data.get("preset", SPECIALIST_PRESET),
            max_turns=data.get("max_turns", SPECIALIST_MAX_TURNS),
            agentic=data.get("agentic", False),
            max_iterations=data.get("max_iterations", AGENTIC_MAX_ITERATIONS),
            skills=data.get("skills", []),
            context_builder=data.get("context_builder"),
        )

    logger.info(f"Loaded {len(registry)} specialists: {list(registry.keys())}")
    return registry


SPECIALISTS: Dict[str, SpecialistConfig] = _load_specialists()

# Human-friendly slash command aliases for specialists.
# These are registered alongside the raw specialist slug when possible.
SPECIALIST_COMMAND_ALIASES: Dict[str, str] = {
    "plan": "planner",
}

SKILLS: List[str] = [
    "red_team",
    "blue_team",
    "pro_con",
    "steelman",
    "devils_advocate",
    "backcast",
    "rubber_duck",
    "eli5",
    "formal",
    "speed",
    "teach",
]


def get_specialist(slug: str) -> Optional[SpecialistConfig]:
    """Get specialist configuration by slug.

    Args:
        slug: Specialist identifier (e.g., "debugger")

    Returns:
        SpecialistConfig if found, None otherwise
    """
    return SPECIALISTS.get(slug)


def list_specialists() -> List[SpecialistConfig]:
    """Get all available specialist configurations.

    Returns:
        List of all SpecialistConfig objects
    """
    return list(SPECIALISTS.values())


def get_specialist_command_map() -> Dict[str, str]:
    """Return slash command name -> specialist slug mapping.

    Includes both the canonical specialist slug and any configured aliases.
    Aliases pointing at missing specialists are ignored.
    """
    mapping: Dict[str, str] = {slug: slug for slug in SPECIALISTS.keys()}
    for alias, slug in SPECIALIST_COMMAND_ALIASES.items():
        if slug in SPECIALISTS:
            mapping[alias] = slug
    return mapping


def render_specialist_prompt(
    specialist: SpecialistConfig,
    task: str,
    context: Optional[str] = None,
    directives: Optional[str] = None,
    skill: Optional[str] = None,
    pk: Optional[str] = None,
    sk: Optional[str] = None,
    injected_context: Optional[str] = None,
) -> str:
    """Render a specialist's prompt template.

    Args:
        specialist: SpecialistConfig object
        task: The task description for the specialist
        context: Optional context/background information
        directives: Optional formatted directives block
        skill: Optional skill mode (red_team, blue_team, pro_con)
        pk: Optional primary key for DynamoDB operations
        sk: Optional sort key for DynamoDB operations

    Returns:
        Rendered prompt string
    """
    prompt = render_template(
        specialist.template,
        task=task,
        context=context or "",
        directives=directives or "",
        skill=skill,
        pk=pk or "operator",
        sk=sk or "program#current",
        injected_context=injected_context or "",
    )

    handoff = render_template("handoff_protocol.j2")
    return f"{prompt}\n\n{handoff}"
