from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import casbin


def _enforcer() -> casbin.Enforcer:
    model = casbin.Model()
    model.load_model_from_text("[request_definition]\nr = sub, obj, act\n[policy_definition]\np = sub, obj, act\n[policy_effect]\ne = some(where (p.eft == allow))\n[matchers]\nm = r.sub == p.sub && r.obj == p.obj && r.act == p.act")
    return casbin.Enforcer(model)


@dataclass(frozen=True)
class AccessContext:
    person: str
    athlete: str
    grant: str | None = None


def _permission(name: str, ownership: str) -> str:
    if ownership == "public":
        return "public:read"
    if ownership == "operator":
        return "operator:write"
    if name.startswith(("grant_create", "grant_revoke")):
        return "grants:admin"
    if name.startswith(("grant_", "profile_")):
        return "profile:read"
    verbs = ("create", "update", "delete", "remove", "replace", "add", "apply", "archive", "publish", "upload", "set", "complete")
    return f"{name}:{'write' if any(verb in name for verb in verbs) else 'read'}"


@lru_cache(maxsize=1)
def permission_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (Path(__file__).parent / "operations").glob("*.json"):
        for record in json.loads(path.read_text()):
            result[record["name"]] = record.get("permission") or _permission(record["name"], record.get("ownership", "athlete"))
    return result


def allowed(operation: str, context: AccessContext, write: bool) -> bool:
    permission = permission_map().get(operation)
    if permission is None or not context.athlete:
        return False
    enforcer = _enforcer()
    subject = "operator" if context.person == "operator" else "athlete" if context.person == context.athlete else context.grant or "guest"
    enforcer.add_policy(subject, permission, "write" if write else "read")
    if enforcer.enforce(subject, permission, "write" if write else "read"):
        return True
    domain = permission.split(":", 1)[0]
    if context.grant == "coach":
        return not write or domain in {"program", "sessions", "competition", "attempts", "analytics", "maxes", "budget"}
    if context.grant == "handler":
        return (not write and domain in {"sessions", "program", "competition", "attempts", "analytics", "budget", "profile"}) or (write and domain in {"competition", "attempts"})
    return False


def evaluate(operation: str, context: AccessContext, write: bool) -> None:
    if not allowed(operation, context, write):
        raise PermissionError(f"permission denied for {operation}")


def self_check() -> None:
    assert allowed("program_get", AccessContext("a", "a"), False)
    assert not allowed("program_get", AccessContext("c", "a"), False)
    assert allowed("competition_update", AccessContext("h", "a", "handler"), True)


if __name__ == "__main__":
    self_check()
