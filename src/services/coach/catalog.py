import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Operation:
    name: str
    domain: str
    description: str
    input_schema: dict[str, Any]
    execution: str

    @property
    def uses_inference(self) -> bool:
        return self.execution == "ai"


@lru_cache
def operations(operations_dir: Path, permissions_path: Path) -> dict[str, Operation]:
    permissions = json.loads(permissions_path.read_text()) if permissions_path.is_file() else {}
    catalog = {}
    for path in sorted(operations_dir.glob("*.json")):
        for record in json.loads(path.read_text()):
            if permissions.get(record["name"], {}).get("internal_only"):
                continue
            catalog[record["name"]] = Operation(
                name=record["name"],
                domain=record["domain"],
                description=record.get("description", ""),
                input_schema=record.get("input_schema") or {"type": "object"},
                execution=record.get("execution", "deterministic"),
            )
    return catalog
