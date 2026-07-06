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

async def template_apply_confirm(sk, backfilled_maxes=None, start_date=None, week_start_day=None, target="new_block", actor_pk=None):
    from .template_apply import concretize
    from .training_weeks import normalize_week_start_day
    from datetime import date, datetime, timezone
    import copy
    ts=_get_template_store(); template=await ts.get_template(sk, actor_pk=actor_pk)
    if not template: raise ValueError(f"Template not found: {sk}")
    store=_get_store(); program=await store.get_program(); current_maxes=dict(program.get("current_maxes",{}))
    rwsd=normalize_week_start_day(week_start_day,"Monday")
    if backfilled_maxes: current_maxes.update(backfilled_maxes)
    glossary=await _get_glossary_store().get_glossary()
    s_date=date.fromisoformat(start_date) if start_date else date.today()
    sessions=concretize(template, current_maxes, glossary, s_date, rwsd)
    for s in sessions: s["block"]="current"
    new_program=copy.deepcopy(program); new_program["sessions"]=sessions; new_program.setdefault("meta",{})
    bwsd=dict(new_program["meta"].get("block_week_start_days") or {}); bwsd["current"]=rwsd
    new_program["meta"]["program_week_start_day"]=rwsd; new_program["meta"]["block_week_start_days"]=bwsd
    new_program["meta"]["template_lineage"]={"applied_template_sk":sk,"applied_at":datetime.now(timezone.utc).isoformat(),"week_start_day":rwsd,"start_date":s_date.isoformat()}
    await store._write_new_version(new_program, minor=False)
    return {"status":"applied","program_version":new_program["meta"].get("version_label"),"program_sk":new_program.get("sk") or new_program["meta"].get("version_label")}
