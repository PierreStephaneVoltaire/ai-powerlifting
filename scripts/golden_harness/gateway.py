import importlib
import os
import sys
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from .safety import assert_local_endpoint

assert_local_endpoint()

DOMAINS = ["program", "sessions", "competition", "federation", "glossary", "goals", "weight-log", "analytics", "performance", "calculations", "lift-profiles"]

ACTOR = {"pk": "operator", "mapped_pk": "operator", "roles": ["athlete"], "active_role": "athlete"}


def load_domain(domain):
    os.environ["PL_DOMAIN"] = domain
    sys.modules.pop("services.app", None)
    return importlib.import_module("services.app").app


root = FastAPI(title="golden harness gateway")


@root.get("/health")
def health():
    return {"status": "ok"}


@root.post("/profile/internal/access")
async def internal_access(arguments: dict[str, Any], x_internal_token: str = Header(default=""), x_pl_principal: str = Header(default="")):
    from services import access, authorization
    from services.dispatch import OperationError
    from services.principal import verify_principal

    if x_internal_token != os.environ["INTERNAL_API_TOKEN"]:
        raise HTTPException(401, "Invalid internal token")
    operation = arguments.get("operation", "")
    try:
        claims = verify_principal(x_pl_principal, operation)
        context = access.evaluate_facts(claims["sub"], claims["athlete"], ACTOR, ACTOR, [], {})
        return authorization.check_context(operation, arguments.get("arguments") or {}, claims, context)
    except OperationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
    except Exception as exc:
        raise HTTPException(401, {"code": "invalid_principal", "message": str(exc)})


def patch_onboarding():
    module = importlib.import_module("services.handlers.user._shared.settings_normalize")
    module.derive_onboarding_status = lambda settings: {"has_athlete_basics": True}


patch_onboarding()
for domain in DOMAINS:
    root.mount(f"/{domain}", load_domain(domain))
os.environ["PL_DOMAIN"] = "analytics"
app = root
