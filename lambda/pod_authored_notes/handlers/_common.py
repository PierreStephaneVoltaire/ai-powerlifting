import os
import json

from services.authored_notes import AuthoredNotesStore, NoteError


def store():
    return AuthoredNotesStore(
        table_name=os.getenv("IF_HEALTH_TABLE_NAME", "if-health"),
        region=os.getenv("AWS_REGION", "ca-central-1"),
    )


def person(args):
    value = args.get("_person_pk")
    if not isinstance(value, str) or not value:
        raise ValueError("Authenticated Person required")
    return value


def athlete(args):
    value = args.get("pk")
    if not isinstance(value, str) or not value:
        raise ValueError("Athlete scope required")
    return value


def access(args):
    return args.get("_access") or {}


def execute(operation):
    try:
        return operation()
    except NoteError as exc:
        details = {"code": exc.code, "message": str(exc)}
        if hasattr(exc, "current_revision"):
            details.update({"current_revision": exc.current_revision, "current_record": exc.current_record})
        return {"statusCode": exc.status, "body": json.dumps(details)}
