_import_store = None
def _get_import_store():
    global _import_store
    if _import_store is None:
        import os
        from import_store import ImportStore
        _import_store = ImportStore(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _import_store

_template_store = None
def _get_template_store():
    global _template_store
    if _template_store is None:
        import os
        from template_store import TemplateStore
        _template_store = TemplateStore(table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME","if-health-templates"), pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK","template_library"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _template_store

_store = None
def _get_store():
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(table_name=os.environ.get("IF_HEALTH_TABLE_NAME","if-health"), pk=os.environ.get("HEALTH_PROGRAM_PK","operator"), region=os.environ.get("AWS_REGION","ca-central-1"))
    return _store

import copy, uuid
def _template_actor(actor_pk):
    return str(actor_pk or _get_store().pk)
def _template_author(author, actor_pk):
    return str(author or actor_pk or _template_actor(actor_pk))
def _template_days_per_week(sessions):
    by_week={}
    for s in sessions:
        try: wn=int(s.get("week_number") or 1)
        except: wn=1
        by_week.setdefault(wn,set()).add(str(s.get("day_index") or s.get("day_of_week") or s.get("label") or "1"))
    return max((len(d) for d in by_week.values()), default=0)
def _template_normalize_day(session):
    wdays=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    day=session.get("day_of_week"); di=session.get("day_index")
    if isinstance(day,str) and day in wdays:
        session["day_index"]=wdays.index(day)+1; return
    try: idx=int(di)
    except: idx=1
    idx=max(1,min(7,idx)); session["day_index"]=idx; session["day_of_week"]=wdays[idx-1]
def _prepare_template_payload(template):
    prepared=copy.deepcopy(template); meta=prepared.setdefault("meta",{}); sessions=prepared.setdefault("sessions",[]); phases=prepared.setdefault("phases",[])
    if not isinstance(sessions,list): prepared["sessions"]=sessions=[]
    if not isinstance(phases,list): prepared["phases"]=[]
    resolved=set(); unresolved=set(); required_maxes=set(); max_week=0
    for s in sessions:
        if not isinstance(s,dict): continue
        s.setdefault("id",str(uuid.uuid4()))
        try: wn=int(s.get("week_number") or 1)
        except: wn=1
        wn=max(1,wn); s["week_number"]=wn; max_week=max(max_week,wn)
        _template_normalize_day(s); s.setdefault("label",f"W{wn}D{s.get('day_index',1)}")
        exs=s.get("exercises")
        if not isinstance(exs,list): s["exercises"]=exs=[]
        for ex in exs:
            if not isinstance(ex,dict): continue
            ex.setdefault("notes",""); ex.setdefault("sets",None); ex.setdefault("reps",None)
            lt=str(ex.get("load_type") or "unresolvable").lower()
            if lt not in {"rpe","percentage","absolute","unresolvable"}: lt="unresolvable"
            ex["load_type"]=lt
            if lt=="percentage":
                try:
                    lv=float(ex.get("load_value"))
                    if lv>1: lv=lv/100.0
                    ex["load_value"]=lv
                except: ex["load_value"]=None; ex["load_type"]="unresolvable"
            gid=ex.get("glossary_id")
            if gid:
                gid=str(gid); ex["glossary_id"]=gid; resolved.add(gid)
                if ex["load_type"] in {"percentage","rpe"}: required_maxes.add(gid)
            else:
                nm=str(ex.get("name") or "").strip()
                if nm: unresolved.add(nm)
    if not max_week: max_week=max([int(s.get("week_number") or 1) for s in sessions if isinstance(s,dict)] or [0])
    meta.setdefault("name","Imported Template"); meta.setdefault("description",""); meta.setdefault("estimated_weeks",max_week); meta.setdefault("days_per_week",_template_days_per_week(sessions)); meta.setdefault("archived",False)
    prepared["required_maxes"]=sorted(required_maxes)
    prepared["glossary_resolution"]={"resolved":sorted(resolved),"unresolved":sorted(unresolved),"auto_added":[],"resolution_status":"partial" if resolved and unresolved else ("unresolved" if unresolved else "resolved")}
    return prepared

async def import_apply(import_id, merge_strategy="append", conflict_resolutions=None, start_date=None, actor_pk=None, author=None):
    import copy
    from datetime import datetime, timezone
    istore=_get_import_store(); pending=await istore.get_pending(import_id)
    if not pending: raise ValueError(f"Import not found: {import_id}")
    if pending.get("status")!="awaiting_review": raise ValueError(f"Import {import_id} has already been {pending.get('status')}")
    itype=pending.get("import_type"); pr=pending.get("ai_parse_result",{})
    if itype=="template":
        template={"meta":{"name":f"Imported {pending.get('source_filename','template').split('.')[0]}","description":pr.get("parse_notes",""),"source_filename":pending.get("source_filename"),"source_file_hash":pending.get("source_file_hash"),"estimated_weeks":max([s.get("week_number",0) for s in pr.get("sessions",[])] or [0]),"days_per_week":4,"archived":False},"phases":pr.get("phases",[]),"sessions":pr.get("sessions",[]),"required_maxes":list(set([ex.get("glossary_id") for s in pr.get("sessions",[]) for ex in s.get("exercises",[]) if ex.get("glossary_id")])),"glossary_resolution":{"resolved":[],"unresolved":[],"auto_added":[],"resolution_status":"resolved"}}
        ts=_get_template_store(); ra=_template_actor(actor_pk)
        sk=await ts.put_template(_prepare_template_payload(template), actor_pk=ra, author=_template_author(author,ra), published=False)
        await istore.mark_applied(import_id, datetime.now(timezone.utc).isoformat())
        return {"status":"applied","target_sk":sk}
    else:
        store=_get_store(); program=await store.get_program(); new_program=copy.deepcopy(program)
        staged=pr.get("sessions",[])
        if not staged: raise ValueError("No sessions found in staged import")
        existing=new_program.get("sessions",[]); emap={s["date"]:s for s in existing}
        resolutions={r["session_date"]:r["action"] for r in (conflict_resolutions or [])}
        applied=0; skipped=0
        for s in staged:
            sd=s.get("date")
            if not sd: continue
            if sd in emap:
                action=resolutions.get(sd, merge_strategy)
                if action=="skip": skipped+=1; continue
                elif action in ("overwrite","replace_planned"): emap[sd].update(s); applied+=1
                elif action in ("merge","append"): emap[sd].setdefault("exercises",[]).extend(s.get("exercises",[])); emap[sd].setdefault("planned_exercises",[]).extend(s.get("planned_exercises",[])); applied+=1
            else: existing.append(s); emap[sd]=s; applied+=1
        new_program["sessions"]=sorted(existing, key=lambda x: x.get("date",""))
        await store._write_new_version(new_program, minor=False)
        await istore.mark_applied(import_id, datetime.now(timezone.utc).isoformat())
        return {"status":"applied","applied_count":applied,"skipped_count":skipped,"new_version":new_program["meta"].get("version_label")}
