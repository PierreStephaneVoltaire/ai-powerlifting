_store = None
def _get_store():
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _store

def health_invalidate_program_cache():
    _get_store().invalidate_cache(); return {"success": True}
