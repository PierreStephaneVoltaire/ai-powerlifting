import asyncio
import json
from decimal import Decimal

from services.dispatch import OperationError

from services.relationships import (
    create_request,
    favorite,
    list_favorites,
    list_notifications,
    list_relationship_history,
    list_requests,
    mark_notifications_read,
    respond_request,
    revoke_relationship,
)


def _json(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return str(value)


def run(function, event):
    args = event.get("args", event)
    try:
        result = asyncio.run(asyncio.to_thread(function, args))
    except OperationError as exc:
        return {"statusCode": exc.status, "body": json.dumps({"code": exc.code, "message": exc.message, **exc.details}, default=_json)}
    return {"statusCode": 200, "body": json.dumps(result, default=_json)}


def request(event):
    return run(create_request, event)


def respond(event):
    return run(respond_request, event)


def revoke(event):
    return run(revoke_relationship, event)


def list_all(event):
    return run(list_requests, event)


def history(event):
    return run(list_relationship_history, event)


def favorite_item(event):
    return run(favorite, event)


def favorites(event):
    return run(list_favorites, event)


def notifications(event):
    return run(list_notifications, event)


def notifications_read(event):
    return run(mark_notifications_read, event)
