import json
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict


JOB_SUBMITTED_SCHEMA = {"type": "object", "properties": {"job_id": {"type": ["string", "null"]}, "generation_id": {"type": "string"}, "status": {"enum": ["starting", "running", "succeeded", "failed", "cancel_requested", "cancelled", "uncertain", "missing"]}}, "required": ["status"], "anyOf": [{"required": ["job_id"]}, {"required": ["generation_id"]}]}


DOMAINS = (
    "program", "sessions", "competition", "federation", "glossary", "goals",
    "budget", "calculations", "performance", "weight-log", "templates",
    "imports", "profile", "lift-profiles", "analytics", "videos",
)


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    domain: str
    description: str
    handler: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    execution: Literal["deterministic", "ai"] = "deterministic"
    ownership: Literal["athlete", "public", "person", "operator"] = "athlete"
    legacy: list[str] = []
    permission: str | None = None

    def validate_input(self, arguments: dict[str, Any]) -> None:
        Draft202012Validator(self.input_schema, format_checker=FormatChecker()).validate(arguments)

    def validate_result(self, result: Any) -> None:
        Draft202012Validator(self.result_schema).validate(result)


def load_operations(domain: str | None = None) -> dict[str, Operation]:
    if domain is not None and domain not in DOMAINS:
        raise ValueError(f"Unknown domain: {domain}")
    operations = {}
    for selected in (domain,) if domain else DOMAINS:
        for record in json.loads((Path(__file__).parent / "operations" / f"{selected}.json").read_text()):
            operation = Operation.model_validate(record)
            if operation.ownership != "public":
                operation.input_schema.setdefault("properties", {}).setdefault("pk", {"type": "string", "minLength": 1})
            if operation.domain != selected or operation.name in operations:
                raise ValueError(f"Invalid or duplicate operation: {operation.name}")
            Draft202012Validator.check_schema(operation.input_schema)
            Draft202012Validator.check_schema(operation.result_schema)
            operations[operation.name] = operation
    return operations
