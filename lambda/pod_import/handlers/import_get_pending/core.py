_import_store = None
def _get_import_store():
    global _import_store
    if _import_store is None:
        import os
        from import_store import ImportStore
        _import_store = ImportStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _import_store

async def import_get_pending(import_id):
    s=_get_import_store(); return await s.get_pending(import_id)