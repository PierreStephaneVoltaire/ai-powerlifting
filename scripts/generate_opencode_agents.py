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


def _clean_template(text: str) -> str:
    text = text.replace("@preset/", "")
    text = text.replace("OpenHands SDK", "opencode")
    text = text.replace("run_subagent_sdk()", "opencode build mode")
    return text.strip()


def render_agent(slug: str, config: dict, template: str, personality: str) -> str:
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
        "You are an opencode specialist replacement for IF. Keep IF's personality and the specialist posture below.",
        "",
        "## IF Personality",
        "",
        personality.strip(),
        "",
        "## Specialist Metadata",
        "",
        f"- Slug: `{slug}`",
        f"- Directive types: {', '.join(directive_types) if directive_types else 'core'}",
        f"- MCP servers: {', '.join(mcp_servers) if mcp_servers else 'none declared'}",
        f"- Tools: {', '.join(tools) if tools else 'none declared'}",
        f"- Skills: {', '.join(skills) if skills else 'none declared'}",
        "",
        "Model selection is supplied by `plan.md`.",
        "",
        "## Specialist Directives",
        "",
        _clean_template(template),
        "",
        "## Output",
        "",
        "Follow the task prompt exactly. For technical work, write the final response to `response.md` when asked by the runner.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    personality = PERSONALITY_PATH.read_text(encoding="utf-8")
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
        template = template_path.read_text(encoding="utf-8")
        output = render_agent(slug, config, template, personality)
        (OUTPUT_DIR / f"{slug}.md").write_text(output, encoding="utf-8")
        written += 1
    print(f"Generated {written} opencode agent files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
