from dataclasses import dataclass
from pathlib import Path

from .catalog import Operation


@dataclass(frozen=True)
class Surface:
    name: str
    scope: str
    operations: frozenset[str]
    subject_argument: str
    instructions: str


TEMPLATE = Surface(
    name="template",
    scope=(
        "One of the person's training templates: questions about its analysis report and AI evaluation, challenging or refining a finding, "
        "revising the template's program context and re-running the evaluation, and editing the template's exercises and prescriptions "
        "(replace, re-prescribe, remove or add exercises in chosen weeks and days)."
    ),
    operations=frozenset({"template_get", "template_report", "template_evaluate", "template_patch"}),
    subject_argument="sk",
    instructions=(Path(__file__).parent / "surfaces" / "template.md").read_text(),
)

SURFACES = {TEMPLATE.name: TEMPLATE}
SURFACE_ONLY = frozenset({"template_patch"})


def tools(catalog: dict[str, Operation], surface: Surface | None) -> dict[str, Operation]:
    if surface is None:
        return {name: operation for name, operation in catalog.items() if name not in SURFACE_ONLY}
    return {name: operation for name, operation in catalog.items() if name in surface.operations}
