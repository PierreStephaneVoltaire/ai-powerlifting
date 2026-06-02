
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

def render_program_summary(program: dict, max_sessions: int = 5) -> str:
  
    lines = []
    
    meta = program.get("meta", {})
    phases = program.get("phases", [])
    sessions = program.get("sessions", [])
    diet_notes = program.get("diet_notes", [])
    supplements = program.get("supplements", [])
    
    current_week = _calculate_current_week(meta.get("program_start", ""))
    total_weeks = _calculate_total_weeks(phases)
    current_phase = _find_current_phase(phases, current_week)
    
    comp_date_str = meta.get("comp_date", "")
    days_to_comp = _calculate_days_to_comp(comp_date_str)
    
    phase_name = current_phase.get("name", "Unknown") if current_phase else "Unknown"
    header = f"## Training Program — Week {current_week} / {total_weeks} ({phase_name})"
    lines.append(header)
    
    comp_display = f"{comp_date_str}" if comp_date_str else "N/A"
    days_display = f"({days_to_comp} days)" if days_to_comp is not None else ""
    target_total = meta.get("target_total_kg")
    target_display = f"{target_total}kg" if target_total else "N/A"
    weight_class = meta.get("weight_class_kg")
    class_display = f"-{weight_class}kg" if weight_class else "N/A"
    
    meta_line = f"**Comp:** {comp_display} {days_display}  |  **Target total:** {target_display}  |  **Class:** {class_display}"
    lines.append(meta_line)
    lines.append("")
    
    if phases:
        lines.append("### Phases")
        lines.append("| Phase | Weeks | Intent |")
        for phase in phases:
            name = phase.get("name", "Unknown")
            start = phase.get("start_week", "?")
            end = phase.get("end_week", "?")
            intent = phase.get("intent", "")
            lines.append(f"| {name} | {start}-{end} | {intent} |")
        lines.append("")
    
    upcoming = _get_upcoming_sessions(sessions, max_sessions)
    if upcoming:
        lines.append(f"### Upcoming Sessions (next {len(upcoming)})")
        lines.append("| Date | Day | Exercises | Notes |")
        for session in upcoming:
            session_date = session.get("date", "")
            day_name = session.get("day", "")
            exercises = session.get("exercises", [])
            exercise_names = ", ".join(e.get("name", "") for e in exercises[:3])
            if len(exercises) > 3:
                exercise_names += "..."
            notes = session.get("session_notes", "")
            if len(notes) > 30:
                notes = notes[:27] + "..."
            lines.append(f"| {session_date} | {day_name} | {exercise_names} | {notes} |")
        lines.append("")
    
    if diet_notes:
        current_diet = diet_notes[-1]
        lines.append("### Diet Protocol (current)")
        diet_text = current_diet.get("notes", "")
        if diet_text:
            lines.append(diet_text)
        lines.append("")
    
    if supplements:
        lines.append("### Supplements")
        for supp in supplements:
            name = supp.get("name", "")
            dose = supp.get("dose", "")
            lines.append(f"- {name}: {dose}")
        lines.append("")
    
    return "\n".join(lines).strip()

def render_session(session: dict) -> str:
    """Render single session as compact markdown.
    
    Used for post-session logging confirmations.
    
    Args:
        session: Session dict with date, exercises, etc.
        
    Returns:
        Compact markdown string for the session
    """
    lines = []
    
    session_date = session.get("date", "")
    day_name = session.get("day", "")
    completed = session.get("completed", False)
    session_rpe = session.get("session_rpe")
    body_weight = session.get("body_weight_kg")
    exercises = session.get("exercises", [])
    notes = session.get("session_notes", "")
    
    lines.append(f"## Session: {session_date} ({day_name})")
    
    if completed:
        status = "Completed"
        if session_rpe:
            status += f" @ RPE {session_rpe}"
    else:
        status = "Pending"
    
    weight_display = f"{body_weight}kg" if body_weight else "N/A"
    lines.append(f"**Status:** {status}  |  **Body Weight:** {weight_display}")
    lines.append("")
    
    if exercises:
        lines.append("### Exercises")
        lines.append("| Exercise | Sets x Reps | Weight | RPE |")
        for ex in exercises:
            name = ex.get("name", "")
            sets = ex.get("sets", "?")
            reps = ex.get("reps", "?")
            kg = ex.get("kg", "")
            weight_str = f"{kg}kg" if kg else ""
            rpe = ex.get("rpe", "")
            lines.append(f"| {name} | {sets}x{reps} | {weight_str} | {rpe} |")
        lines.append("")
    
    if notes:
        lines.append(f"**Notes:** {notes}")
    
    return "\n".join(lines).strip()

def _calculate_current_week(program_start: str) -> int:
    """Calculate current training week from program start date.
    
    Args:
        program_start: ISO8601 date string (YYYY-MM-DD)
        
    Returns:
        Current week number (1-indexed), defaults to 1 if cannot calculate
    """
    if not program_start:
        return 1
    
    try:
        start = datetime.strptime(program_start, "%Y-%m-%d").date()
        today = date.today()
        days_since = (today - start).days
        return max(1, (days_since // 7) + 1)
    except ValueError:
        return 1

def _calculate_total_weeks(phases: list[dict]) -> int:
    """Calculate total program weeks from phases.
    
    Args:
        phases: List of phase dicts with start_week and end_week
        
    Returns:
        Total weeks across all phases, defaults to 12 if no phases
    """
    if not phases:
        return 12
    
    max_week = 0
    for phase in phases:
        end_week = phase.get("end_week", 0)
        if end_week > max_week:
            max_week = end_week
    
    return max_week if max_week > 0 else 12

def _find_current_phase(phases: list[dict], current_week: int) -> Optional[dict]:
    """Find the phase containing the current week.
    
    Args:
        phases: List of phase dicts with start_week and end_week
        current_week: Current training week number
        
    Returns:
        Phase dict if found, None otherwise
    """
    for phase in phases:
        start = phase.get("start_week", 0)
        end = phase.get("end_week", 0)
        if start <= current_week <= end:
            return phase
    return None

def _calculate_days_to_comp(comp_date_str: str) -> Optional[int]:
    """Calculate days until competition.
    
    Args:
        comp_date_str: ISO8601 date string (YYYY-MM-DD)
        
    Returns:
        Days until competition, None if cannot calculate
    """
    if not comp_date_str:
        return None
    
    try:
        comp_date = datetime.strptime(comp_date_str, "%Y-%m-%d").date()
        today = date.today()
        return (comp_date - today).days
    except ValueError:
        return None

def _get_upcoming_sessions(sessions: list[dict], max_sessions: int) -> list[dict]:
    """Get upcoming sessions (date >= today).
    
    Args:
        sessions: List of session dicts
        max_sessions: Maximum number of sessions to return
        
    Returns:
        List of upcoming session dicts, sorted by date
    """
    today = date.today()
    upcoming = []
    
    for session in sessions:
        session_date_str = session.get("date", "")
        if not session_date_str:
            continue
        
        try:
            session_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
            if session_date >= today:
                upcoming.append(session)
        except ValueError:
            continue
    
    upcoming.sort(key=lambda s: s.get("date", ""))
    
    return upcoming[:max_sessions]
