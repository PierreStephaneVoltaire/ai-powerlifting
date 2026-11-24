import importlib
from pathlib import Path

from services.runtime.contract import load_operations
import services.runtime.dispatch

NATIVE_DOMAINS = {"performance", "federation", "goals", "weight-log", "calculations", "analytics", "analytics-ai", "analytics-export", "rankings", "sessions", "program", "competition", "profile", "glossary", "lift-profiles", "export"}


def test_every_registered_handler_imports_with_service_dependencies():
    operations_dir = Path(__file__).resolve().parents[2] / "operations"
    for operation_file in sorted(operations_dir.glob("*.json")):
        if operation_file.stem in NATIVE_DOMAINS:
            continue
        for operation in load_operations(operation_file.stem).values():
            if operation.handler is None:
                continue
            module = importlib.import_module(operation.handler)
            assert callable(module.handler), operation.name
