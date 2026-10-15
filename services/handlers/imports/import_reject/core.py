import os
from datetime import datetime, timezone

from .._import_store import ImportStore


def _get_import_store(pk=None):
    return ImportStore(
        os.getenv("IF_HEALTH_TABLE_NAME", "if-health"),
        pk or os.getenv("HEALTH_PROGRAM_PK", "operator"),
        os.getenv("AWS_REGION", "ca-central-1"),
    )


async def import_reject(args, reason=None):
    if isinstance(args, str):
        import_id = args
        store = _get_import_store()
    else:
        import_id = args["import_id"]
        reason = args.get("reason")
        store = _get_import_store(args["pk"])
    await store.mark_rejected(import_id, reason)
    return {"status": "rejected", "import_id": import_id}
