
from __future__ import annotations

import uuid
from typing import Any

def derive_week_number(session: dict[str, Any], program: dict[str, Any]) -> int:
    """Return the 1-based week number of a session relative to program start."""
    meta = program.get("meta", {})
    start_date_str = meta.get("program_start")
    if not start_date_str:
        return int(session.get("week_number") or 1)
    
    from datetime import date
    start_date = date.fromisoformat(start_date_str)
    curr_date = date.fromisoformat(session["date"])
    
    delta = curr_date - start_date
    return (delta.days // 7) + 1

def derive_day_index(session: dict[str, Any], program: dict[str, Any]) -> int:
    """Return a 1-based day index (1-7) for ordering sessions within a week."""
    from datetime import date
    d = date.fromisoformat(session["date"])
    return d.weekday() + 1

def derive_week_count(program: dict[str, Any]) -> int:
    sessions = program.get("sessions", [])
    if not sessions:
        return 0
    nums = [derive_week_number(s, program) for s in sessions if s.get("date")]
    return max(nums) if nums else 0

def derive_days_per_week(program: dict[str, Any]) -> int:
    sessions = program.get("sessions", [])
    if not sessions:
        return 0
    
    weeks: dict[int, int] = {}
    for s in sessions:
        if not s.get("date"): continue
        w = derive_week_number(s, program)
        weeks[w] = weeks.get(w, 0) + 1
    
    return max(weeks.values()) if weeks else 0

def convert_block_to_template(program: dict[str, Any], e1rm_map: dict[str, float]) -> dict[str, Any]:
    """Convert a program block into a reusable template."""
    sessions = []
    
    for session in program.get("sessions", []):
        if session.get("completed") or session.get("status") in ("logged", "completed"):
            continue
            
        tpl_exercises = []
        exercises = session.get("planned_exercises") or session.get("exercises") or []
        
        for ex in exercises:
            name = ex.get("name")
            if not name: continue
            
            kg = ex.get("kg") or 0
            rpe = ex.get("rpe_target") or ex.get("rpe")
            e1rm = e1rm_map.get(name)
            load_source = ex.get("load_source", "absolute")
            
            if load_source == "rpe" or (kg == 0 and rpe):
                tpl_ex_fields = {
                    "load_type": "rpe",
                    "load_value": None,
                    "rpe_target": rpe
                }
            elif kg > 0 and e1rm and e1rm > 0:
                tpl_ex_fields = {
                    "load_type": "percentage",
                    "load_value": round(float(kg) / e1rm, 3),
                    "rpe_target": rpe
                }
            elif kg > 0:
                tpl_ex_fields = {
                    "load_type": "absolute",
                    "load_value": kg,
                    "rpe_target": rpe
                }
            else:
                tpl_ex_fields = {
                    "load_type": "unresolvable",
                    "load_value": None,
                    "rpe_target": None
                }
                
            tpl_exercises.append({
                "name": name,
                "glossary_id": ex.get("glossary_id"),
                "sets": ex.get("sets"),
                "reps": ex.get("reps"),
                "notes": ex.get("notes", ""),
                **tpl_ex_fields
            })
            
        sessions.append({
            "id": f"tpl_{uuid.uuid4()}",
            "week_number": derive_week_number(session, program),
            "day_of_week": session.get("day"),
            "day_index": derive_day_index(session, program),
            "label": session.get("week", ""),
            "exercises": tpl_exercises
        })
        
    sessions.sort(key=lambda s: (s["week_number"], s["day_index"]))
    
    return {
        "meta": {
            "name": f"Template from {program['meta'].get('program_name', 'Block')}",
            "description": f"Automatically converted from program {program.get('sk')}",
            "estimated_weeks": derive_week_count(program),
            "days_per_week": derive_days_per_week(program),
            "archived": False,
            "derived_from_program_sk": program["sk"]
        },
        "phases": program.get("phases", []),
        "sessions": sessions,
        "required_maxes": list(e1rm_map.keys()),
        "glossary_resolution": {
            "resolved": [ex.get("name") for s in sessions for ex in s["exercises"] if ex.get("glossary_id")],
            "unresolved": [ex.get("name") for s in sessions for ex in s["exercises"] if not ex.get("glossary_id")],
            "auto_added": [],
            "resolution_status": "partial"
        }
    }
