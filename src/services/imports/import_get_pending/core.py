import os

from .._import_store import ImportStore


def _get_import_store(pk=None):
    return ImportStore(
        os.getenv("IF_HEALTH_TABLE_NAME", "if-health"),
        pk or os.getenv("HEALTH_PROGRAM_PK", "operator"),
        os.getenv("AWS_REGION", "ca-central-1"),
    )


async def import_get_pending(args):
    if isinstance(args, str):
        return await _get_import_store().get_pending(args)
    return await _get_import_store(args["pk"]).get_pending(args["import_id"])
