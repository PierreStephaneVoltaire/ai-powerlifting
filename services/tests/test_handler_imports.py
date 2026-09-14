import importlib
from pathlib import Path

from services.contract import load_operations
import services.dispatch


def test_every_registered_handler_imports_with_service_dependencies():
    operations_dir = Path(__file__).resolve().parents[1] / "operations"
    for operation_file in sorted(operations_dir.glob("*.json")):
        for operation in load_operations(operation_file.stem).values():
            module = importlib.import_module(operation.handler)
            assert callable(module.handler), operation.name
