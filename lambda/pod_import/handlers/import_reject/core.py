_import_store = None
def _get_import_store():
    global _import_store
    if _import_store is None:
        import os
        from _import_store import ImportStore
        _import_store = ImportStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _import_store

async def import_reject(import_id, reason=None):
    s=_get_import_store(); await s.mark_rejected(import_id, reason); return {"status":"rejected","import_id":import_id}