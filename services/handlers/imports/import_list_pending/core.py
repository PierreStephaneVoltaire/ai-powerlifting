import os

from .._import_store import ImportStore


def _get_import_store(pk=None):
    return ImportStore(
        os.getenv("IF_HEALTH_TABLE_NAME", "if-health"),
        pk or os.getenv("HEALTH_PROGRAM_PK", "operator"),
        os.getenv("AWS_REGION", "ca-central-1"),
    )


async def import_list_pending(args=None):
    if isinstance(args, str) or args is None:
        return await _get_import_store().list_pending(args)
    return await _get_import_store(args["pk"]).list_pending(args.get("import_type"))
