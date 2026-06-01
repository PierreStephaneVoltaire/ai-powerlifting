
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

def main() -> None:
    plugin_dir = Path(__file__).parent
    tool_path = plugin_dir / "tool.py"

    if not tool_path.exists():
        json.dump({"ok": False, "error": f"tool.py not found in {plugin_dir}"}, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    spec = importlib.util.spec_from_file_location("plugin_tool", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    line = sys.stdin.readline()
    if not line:
        json.dump({"ok": False, "error": "Empty stdin"}, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    req = json.loads(line)
    result = asyncio.run(mod.execute(req["name"], req.get("args", {})))

    json.dump({"ok": True, "result": str(result)}, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        json.dump(
            {"ok": False, "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"},
            sys.stdout,
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
