_store = None
def _get_store():
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _store

_template_store = None
def _get_template_store():
    global _template_store
    if _template_store is None:
        import os
        from template_store import TemplateStore
        _template_store = TemplateStore(table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME","if-health-templates"), pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK","template_library"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _template_store

_glossary_store = None
def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        import os
        from glossary_store import GlossaryStore
        _glossary_store = GlossaryStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _glossary_store

async def template_apply(sk, target="new_block", start_date=None, week_start_day=None, actor_pk=None):
    from template_apply import check_max_resolution_gate, concretize
    from training_weeks import normalize_week_start_day
    from datetime import date
    ts=_get_template_store(); template=await ts.get_template(sk, actor_pk=actor_pk)
    if not template: raise ValueError(f"Template not found: {sk}")
    store=_get_store(); program=await store.get_program(); current_maxes=program.get("current_maxes",{})
    rwsd=normalize_week_start_day(week_start_day,"Monday")
    glossary=await _get_glossary_store().get_glossary()
    missing=check_max_resolution_gate(template, current_maxes, glossary)
    if missing:
        return {"status":"gate_blocked","missing_exercises":missing,"missing_maxes":missing,"target":target,"start_date":start_date,"week_start_day":rwsd}
    s_date=date.fromisoformat(start_date) if start_date else date.today()
    sessions=concretize(template, current_maxes, glossary, s_date, rwsd)
    return {"status":"ready","preview_sessions":sessions[:5],"target":target,"start_date":s_date.isoformat(),"week_start_day":rwsd}
