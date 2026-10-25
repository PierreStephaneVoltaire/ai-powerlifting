import json
import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .model import Model, ModelError


ATTEMPTS = 3
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return json.dumps(content, default=str)


def challenge_schema(challenge: dict[str, Any]) -> dict[str, Any] | None:
    tools = challenge.get("tools") or []
    if tools:
        return tools[0].get("function", {}).get("parameters")
    return ((challenge.get("response_format") or {}).get("json_schema") or {}).get("schema")


def _parse(text: str) -> Any:
    return json.loads(FENCE.sub("", text.strip()))


async def answer_challenge(model: Model, challenge: dict[str, Any]) -> Any:
    messages = challenge.get("messages") or []
    system = "\n\n".join(_text(m.get("content")) for m in messages if m.get("role") in {"system", "developer"})
    conversation = "\n\n".join(f"[{m.get('role')}]\n{_text(m.get('content'))}" for m in messages if m.get("role") not in {"system", "developer"})
    schema = challenge_schema(challenge)
    if not schema:
        return await model.complete(system, conversation)
    instructions = system + "\n\nReply with exactly one JSON object and nothing else. It must validate against this JSON Schema:\n" + json.dumps(schema)
    validator = Draft202012Validator(schema)
    prompt = conversation
    for _ in range(ATTEMPTS):
        text = await model.complete(instructions, prompt)
        try:
            value = _parse(text)
            validator.validate(value)
            return value
        except (ValueError, ValidationError) as exc:
            reason = exc.message if isinstance(exc, ValidationError) else str(exc)
            prompt = conversation + "\n\nYour previous reply was rejected: " + reason + "\nPrevious reply:\n" + text[:4000]
    raise ModelError("invalid_output", "Model did not produce schema-valid output")
