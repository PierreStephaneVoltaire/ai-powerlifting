"""Debug IF system prompt — inspect directive injection without app dependencies.

Only requires: boto3, pyyaml (pip install boto3 pyyaml)

Usage:
    python scripts/debug_system_prompt.py                     # main agent + all specialist breakdowns
    python scripts/debug_system_prompt.py --specialist coder  # one specialist
    python scripts/debug_system_prompt.py --full              # full assembled prompt
    python scripts/debug_system_prompt.py --json              # JSON dump of all directives
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
APP_DIR = REPO_ROOT / "app"
SYSTEM_PROMPT_PATH = APP_DIR / "main_system_prompt.txt"
SPECIALISTS_DIR = REPO_ROOT / "specialists"

TABLE_NAME = "if-core"
AWS_REGION = "ca-central-1"
MAIN_AGENT_ONLY_TYPES = {"tool", "memory", "metacognition"}

@dataclass
class Directive:
    alpha: int
    beta: int
    label: str
    content: str
    types: list[str] = field(default_factory=lambda: ["core"])
    version: int = 1
    active: bool = True
    created_by: str = "operator"

    @property
    def base_key(self) -> str:
        return f"{self.alpha:02d}#{self.beta:02d}"

    @classmethod
    def from_item(cls, item: dict) -> "Directive":
        sk = item["sk"]
        m = re.match(r"(\d{2})#(\d{2})#v(\d{3})", sk)
        if not m:
            raise ValueError(f"Invalid SK: {sk}")
        raw = item.get("dtype")
        if isinstance(raw, set):
            types = list(raw)
        elif isinstance(raw, list):
            types = raw
        else:
            types = ["core"]
        return cls(
            alpha=int(m.group(1)), beta=int(m.group(2)), version=int(m.group(3)),
            label=item.get("label", ""), content=item.get("content", ""),
            types=types, active=item.get("active", True),
            created_by=item.get("created_by", "operator"),
        )

def load_directives() -> List[Directive]:
    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)
    resp = table.query(KeyConditionExpression=Key("pk").eq("operator"))
    items = resp.get("Items", [])

    by_key: Dict[str, List[Directive]] = defaultdict(list)
    for item in items:
        try:
            d = Directive.from_item(item)
            by_key[d.base_key].append(d)
        except ValueError:
            pass

    directives = []
    for versions in by_key.values():
        active = [v for v in versions if v.active]
        if active:
            active.sort(key=lambda d: d.version, reverse=True)
            directives.append(active[0])

    directives.sort(key=lambda d: (d.alpha, d.beta))
    return directives

def format_for_prompt(directives: List[Directive]) -> str:
    lines = []
    for d in directives:
        lines.append(f"{d.alpha}-{d.beta}  {d.label} (Directive {num_text(d.alpha)}-{num_text(d.beta)})")
        lines.append(d.content)
        lines.append("")
    return "\n".join(lines)

def get_for_subagent(directives: List[Directive], types: List[str]) -> List[Directive]:
    """Tier 0 always + type matches, minus main-agent-only exclusions."""
    type_set = set(types) if types else set()
    by_key: Dict[tuple, Directive] = {}
    for d in directives:
        if not d.active:
            continue
        d_types = set(d.types)
        if d.alpha == 0:
            by_key[(d.alpha, d.beta)] = d
            continue
        if d_types.issubset(MAIN_AGENT_ONLY_TYPES):
            continue
        if d_types & type_set:
            by_key[(d.alpha, d.beta)] = d
    result = list(by_key.values())
    result.sort(key=lambda d: (d.alpha, d.beta))
    return result

@dataclass
class SpecialistInfo:
    slug: str
    directive_types: List[str]

def discover_specialists() -> Dict[str, SpecialistInfo]:
    specs = {}
    if not SPECIALISTS_DIR.exists():
        return specs
    for d in sorted(SPECIALISTS_DIR.iterdir()):
        yaml_path = d / "specialist.yaml"
        if d.is_dir() and yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
            specs[d.name] = SpecialistInfo(
                slug=d.name,
                directive_types=data.get("directive_types", ["core"]),
            )
    return specs

def num_text(n: int) -> str:
    try:
        from num2words import num2words
        return num2words(n).title()
    except ImportError:
        words = {
            0: "Zero", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
            6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
            11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen",
            15: "Fifteen", 16: "Sixteen", 17: "Seventeen", 18: "Eighteen",
            19: "Nineteen", 20: "Twenty",
        }
        return words.get(n, str(n))

def assemble_full_prompt(directives: List[Directive]) -> str:
    parts = []

    if SYSTEM_PROMPT_PATH.exists():
        parts.append(SYSTEM_PROMPT_PATH.read_text())
    else:
        parts.append("[main_system_prompt.txt not found]")

    block = format_for_prompt(directives)
    if block:
        parts.append(
            f"\n{'='*40}\nDIRECTIVES\n{'='*40}\n{block}"
        )

    parts.append("""
MEMORY PROTOCOL:
You have access to a persistent memory store containing facts
about the operator — preferences, life events, profession,
skill levels, opinions, mental state, and similar context.

USE memory_search WHEN:
  - The conversation would benefit from knowing the operator's
    background, preferences, or history.
  - The operator references something previously discussed
    across sessions.

USE memory_add WHEN:
  - The operator shares personal information with cross-session
    value (preferences, life events, opinions).
  - The operator explicitly asks you to remember something.
""")

    parts.append("""
MEDIA PROTOCOL:
When the operator sends files or images, they appear as [Attachment: filename — uploads/filename].
The file is stored in your terminal workspace under uploads/.

USE read_media WHEN:
  - You need to examine the contents of an image or file
  - The operator asks about a specific attachment
""")

    return "\n".join(parts)

def main():
    p = argparse.ArgumentParser(description="Debug IF directive injection")
    p.add_argument("--specialist", help="Show directives for one specialist")
    p.add_argument("--all-specialists", action="store_true")
    p.add_argument("--full", action="store_true", help="Print full assembled system prompt")
    p.add_argument("--json", action="store_true", help="JSON dump all directives")
    args = p.parse_args()

    print(f"Loading directives from DynamoDB table '{TABLE_NAME}' (region {AWS_REGION})...")
    directives = load_directives()
    print(f"Loaded {len(directives)} active directives\n")

    if args.json:
        print(json.dumps([
            {"alpha": d.alpha, "beta": d.beta, "version": d.version,
             "label": d.label, "types": sorted(d.types), "content": d.content}
            for d in directives
        ], indent=2))
        return

    by_alpha: Dict[int, List[Directive]] = defaultdict(list)
    for d in directives:
        by_alpha[d.alpha].append(d)
    print("Directives by tier:")
    for a in sorted(by_alpha):
        print(f"  Alpha {a}: {len(by_alpha[a])} directives")
    all_types = sorted({t for d in directives for t in d.types})
    print(f"\nAll types in use: {', '.join(all_types)}\n")

    print("=" * 90)
    print(f" MAIN AGENT — gets ALL {len(directives)} directives via format_for_prompt()")
    print("=" * 90)
    for d in directives:
        ts = ", ".join(sorted(d.types))
        print(f"  {d.alpha}-{d.beta}  v{d.version}  [{ts}]  {d.label}")
        preview = d.content[:100].replace("\n", " ")
        suffix = "..." if len(d.content) > 100 else ""
        print(f"         {preview}{suffix}\n")

    specs = discover_specialists()
    targets = {}
    if args.specialist:
        if args.specialist not in specs:
            print(f"Unknown specialist '{args.specialist}'. Available: {', '.join(sorted(specs))}")
            sys.exit(1)
        targets[args.specialist] = specs[args.specialist]
    elif args.all_specialists or not args.specialist:
        targets = specs

    if targets and (args.all_specialists or args.specialist):
        for slug in sorted(targets):
            spec = targets[slug]
            filtered = get_for_subagent(directives, spec.directive_types)
            print("-" * 90)
            print(f" SPECIALIST: {slug}")
            print(f" directive_types: {spec.directive_types}")
            print(f" Matched directives: {len(filtered)}")
            print("-" * 90)
            if not filtered:
                print("  (none matched)\n")
                continue
            for d in filtered:
                ts = ", ".join(sorted(d.types))
                reason = "tier 0 (always)" if d.alpha == 0 else f"types: {', '.join(sorted(set(d.types) & set(spec.directive_types)))}"
                print(f"  {d.alpha}-{d.beta}  [{ts}]  {d.label}  ← {reason}")
            print()

    if args.full:
        print("\n" + "=" * 90)
        print(" FULL ASSEMBLED SYSTEM PROMPT")
        print("=" * 90)
        prompt = assemble_full_prompt(directives)
        print(prompt)
        print(f"\n{'='*90}")
        print(f" Total: {len(prompt):,} chars")
        print(f"{'='*90}")

if __name__ == "__main__":
    main()
