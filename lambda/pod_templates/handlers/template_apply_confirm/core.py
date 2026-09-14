_store = None
def _get_store(actor_pk):
    import os
    from program_store import ProgramStore as _PS
    _store = _PS(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=actor_pk, region=os.environ.get("AWS_REGION","ca-central-1"))
    return _store

_template_store = None
def _get_template_store():
    import os
    from template_store import TemplateStore
    _template_store = TemplateStore(table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME","if-health-templates"), pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK","template_library"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _template_store

_glossary_store = None
def _get_glossary_store(actor_pk):
    import os
    from glossary_store import GlossaryStore
    _glossary_store = GlossaryStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=actor_pk, region=os.environ.get("AWS_REGION","ca-central-1"))
    return _glossary_store

async def template_apply_confirm(sk, backfilled_maxes=None, start_date=None, week_start_day=None, target="new_block", actor_pk=None, block_id=None, block_name=None):
    from .template_apply import concretize
    from .training_weeks import normalize_week_start_day
    from datetime import date, datetime, timezone
    import copy
    ts=_get_template_store(); template=await ts.get_template(sk, actor_pk=actor_pk)
    if not template: raise ValueError(f"Template not found: {sk}")
    store=_get_store(actor_pk); program=await store.get_program(); current_maxes=dict(program.get("current_maxes",{}))
    rwsd=normalize_week_start_day(week_start_day,"Monday")
    if backfilled_maxes: current_maxes.update(backfilled_maxes)
    glossary=await _get_glossary_store(actor_pk).get_glossary()
    s_date=date.fromisoformat(start_date) if start_date else date.today()
    sessions=concretize(template, current_maxes, glossary, s_date, rwsd)
    if target not in {"new_block", "append", "replace_incomplete"}:
        raise ValueError("target must be new_block, append, or replace_incomplete")
    block_id = str(block_id or "current")
    for s in sessions:
        s["block"] = block_id
    existing_sessions = list(program.get("sessions") or [])
    if target == "append":
        merged_sessions = existing_sessions + sessions
    elif target == "replace_incomplete":
        incoming_dates = {str(s.get("date")) for s in sessions}
        merged_sessions = [s for s in existing_sessions if str(s.get("date")) not in incoming_dates or s.get("completed") or s.get("status") in {"logged", "completed"}]
        merged_sessions.extend(sessions)
    else:
        merged_sessions = existing_sessions + sessions
    new_program=copy.deepcopy(program); new_program["sessions"]=merged_sessions; new_program.setdefault("meta",{})
    blocks = list(new_program["meta"].get("blocks") or [])
    if not any(str(b.get("id") or b.get("block_id")) == block_id for b in blocks if isinstance(b, dict)):
        blocks.append({"id": block_id, "block_id": block_id, "name": block_name or block_id, "status": "active", "start_date": s_date.isoformat(), "week_start_day": rwsd, "start_maxes_kg": dict(current_maxes)})
    new_program["meta"]["blocks"] = blocks
    bwsd=dict(new_program["meta"].get("block_week_start_days") or {}); bwsd["current"]=rwsd
    new_program["meta"]["program_week_start_day"]=rwsd; new_program["meta"]["block_week_start_days"]=bwsd
    new_program["meta"]["template_lineage"]={"applied_template_sk":sk,"applied_at":datetime.now(timezone.utc).isoformat(),"week_start_day":rwsd,"start_date":s_date.isoformat()}
    await store._write_new_version(new_program, minor=False)
    return {"status":"applied","program_version":new_program["meta"].get("version_label"),"program_sk":new_program.get("sk") or new_program["meta"].get("version_label"),"target":target,"block_id":block_id,"preserved_sessions":len(existing_sessions)}
