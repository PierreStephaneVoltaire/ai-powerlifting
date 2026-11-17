import json
import sys
from pathlib import Path


CHUNK_SIZE = 8000


def response(request, data):
    return {"jsonrpc": "2.0", "id": request["id"], "result": data}


def handle(request, content):
    method = request.get("method")
    if "id" not in request:
        return None
    if method == "initialize":
        return response(request, {"protocolVersion": request["params"]["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "job-input", "version": "1"}})
    if method == "tools/list":
        return response(request, {"tools": [{"name": "read_input", "description": "Read a part of the current job input. Start at offset 0 and continue until next_offset is null.", "inputSchema": {"type": "object", "properties": {"offset": {"type": "integer", "minimum": 0}}, "required": ["offset"], "additionalProperties": False}, "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}]})
    if method == "tools/call" and request.get("params", {}).get("name") == "read_input":
        offset = request["params"].get("arguments", {}).get("offset")
        if isinstance(offset, int) and not isinstance(offset, bool) and 0 <= offset <= len(content):
            end = min(offset + CHUNK_SIZE, len(content))
            value = json.dumps({"text": content[offset:end], "next_offset": end if end < len(content) else None}, ensure_ascii=False)
            return response(request, {"content": [{"type": "text", "text": value}]})
    return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32602, "message": "Invalid request"}}


def main():
    content = Path(sys.argv[1]).read_text(encoding="utf-8")
    for line in sys.stdin:
        request = json.loads(line)
        result = handle(request, content)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
