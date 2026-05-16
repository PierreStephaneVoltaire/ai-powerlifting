#!/usr/bin/env python3
"""Generate opencode agent markdown files from IF specialists."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS_DIR = ROOT / "specialists"
OUTPUT_DIR = ROOT / ".opencode" / "agent"
PERSONALITY_PATH = ROOT / "app" / "main_system_prompt.txt"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def render_agent(slug: str, config: dict) -> str:
    description = " ".join(str(config.get("description", slug)).split())
    tools = config.get("tools") or []
    mcp_servers = config.get("mcp_servers") or []
    directive_types = config.get("directive_types") or ["core"]
    skills = config.get("skills") or []

    lines = [
        "---",
        f"description: {description[:500]!r}",
        "mode: subagent",
        "permission:",
        "  read: allow",
        "  edit: allow",
        "  bash: allow",
        "---",
        "",
        f"# {slug}",
        "",
        f"This file is generated from `specialists/{slug}/specialist.yaml`.",
        "Do not hardcode IF personality, runtime directives, or model policy here.",
        "The IF runtime injects the live personality from `app/main_system_prompt.txt`,",
        f"renders `specialists/{slug}/agent.j2`, and injects current DynamoDB directives",
        "in the task prompt for each opencode run.",
        "",
        "## Specialist Metadata",
        "",
        f"- Slug: `{slug}`",
        f"- Template: `specialists/{slug}/agent.j2`",
        f"- Directive types: {', '.join(directive_types) if directive_types else 'core'}",
        f"- MCP servers: {', '.join(mcp_servers) if mcp_servers else 'none declared'}",
        f"- Tools: {', '.join(tools) if tools else 'none declared'}",
        f"- Skills: {', '.join(skills) if skills else 'none declared'}",
        "",
        "Model selection is supplied by `plan.md`; do not use preset aliases or @preset names.",
        "",
        "## Runtime Contract",
        "",
        "- Read `history.md` when the runner tells you to use conversation context.",
        "- Follow the live IF personality, rendered specialist prompt, and directive block in the task prompt.",
        "- Use only tools explicitly exposed in the task prompt, normally through the MCP shell bridge.",
        "- Append concise progress lines to `.if/status.log` when doing long operations or tool calls.",
        "- Write the final user-facing response to `response.md` when requested.",
        "",
        "## Output",
        "",
        "Follow the task prompt exactly. For technical work, write the final response to `response.md` when asked by the runner.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not PERSONALITY_PATH.exists():
        raise FileNotFoundError(PERSONALITY_PATH)
    written = 0
    for specialist_dir in sorted(SPECIALISTS_DIR.iterdir()):
        if not specialist_dir.is_dir():
            continue
        config_path = specialist_dir / "specialist.yaml"
        template_path = specialist_dir / "agent.j2"
        if not config_path.exists() or not template_path.exists():
            continue
        slug = specialist_dir.name
        config = _load_yaml(config_path)
        output = render_agent(slug, config)
        (OUTPUT_DIR / f"{slug}.md").write_text(output, encoding="utf-8")
        written += 1
    print(f"Generated {written} opencode agent files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
