import os
from decimal import Decimal

from .._import_store import ImportStore


def _get_import_store(pk):
    return ImportStore(
        os.getenv("IF_HEALTH_TABLE_NAME", "if-health"),
        pk,
        os.getenv("AWS_REGION", "ca-central-1"),
    )


def _number(value, default=0):
    if isinstance(value, (int, Decimal)):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _summary(item):
    return {
        "sk": item.get("sk"),
        "id": item.get("id", item.get("import_id", "")),
        "filename": item.get("filename", item.get("source_filename", "")),
        "source": item.get("source", ""),
        "format": item.get("format", item.get("import_type", "")),
        "status": item.get("status", ""),
        "classification": item.get("classification", ""),
        "row_count": _number(item.get("row_count")),
        "session_count": _number(item.get("session_count")),
        "created_at": item.get("created_at", item.get("uploaded_at", "")),
        "updated_at": item.get("updated_at", ""),
    }


async def import_list(args):
    items = await _get_import_store(args["pk"]).list_imports()
    limit = max(1, min(500, _number(args.get("limit"), 100)))
    summaries = [_summary(item) for item in sorted(items, key=lambda item: item.get("sk", ""), reverse=True)]
    return {"imports": summaries[:limit], "count": min(len(summaries), limit), "total": len(summaries)}
