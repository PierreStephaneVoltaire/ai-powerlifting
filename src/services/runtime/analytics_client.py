import json
import os
from decimal import Decimal
from typing import Any

import httpx

from .ai import current_execution
from .dispatch import OperationError
from services.runtime.storage_scope import current_athlete, current_person

DOMAIN = "analytics"
TIMEOUT_SECONDS = 60


def _service_url() -> str:
    template = os.getenv("PL_SERVICE_URL_TEMPLATE", "http://pl-{domain}:8000")
    return template.format(domain=DOMAIN).rstrip("/")


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def _headers(person: str, athlete: str) -> dict[str, str]:
    headers = {"X-Person-Pk": person, "X-Athlete-Pk": athlete, "Content-Type": "application/json"}
    execution = current_execution.get()
    if execution is not None and execution.job_id:
        headers["X-IF-Turn-Id"] = execution.job_id
        headers["X-PL-Nested-Operation"] = "true"
    return headers


def _failure(response: httpx.Response) -> OperationError:
    try:
        detail = response.json().get("detail", response.text)
    except (ValueError, AttributeError):
        detail = response.text
    return OperationError(response.status_code, "analytics_unavailable", f"Analytics service returned {response.status_code}: {detail}")


def call(operation: str, arguments: dict[str, Any], *, athlete: str | None = None, person: str | None = None) -> Any:
    athlete = athlete or current_athlete.get()
    person = person or current_person.get() or athlete
    if not athlete or not person:
        raise OperationError(403, "forbidden", "Athlete and Person scope required for analytics")
    body = json.dumps({key: value for key, value in arguments.items() if value is not None}, default=_json_default)
    try:
        response = httpx.post(f"{_service_url()}/operations/{operation}", content=body, headers=_headers(person, athlete), timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as error:
        raise OperationError(503, "analytics_unavailable", f"Analytics service unreachable: {error}") from error
    if response.is_error:
        raise _failure(response)
    return response.json()


def weekly_analysis(program: dict | None = None, sessions: list[dict] | None = None, **params: Any) -> dict:
    return call("weekly_analysis", {"program": program, "sessions": sessions, **params})


def estimated_maxes() -> dict:
    return weekly_analysis(block="")["current_maxes"]


def projected_meet(program: dict, comp_date: str, reference_date: str) -> dict | None:
    report = weekly_analysis(program=program, block="", ref_date=reference_date, projection_date=comp_date)
    return report.get("requested_projection")
