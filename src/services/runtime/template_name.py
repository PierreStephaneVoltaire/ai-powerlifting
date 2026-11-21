from pathlib import PureWindowsPath
from textwrap import shorten


def imported_template_name(meta):
    description = str(meta.get("description") or "").strip().split("\n", 1)[0]
    filename = PureWindowsPath(meta.get("source_filename") or "").stem.replace("_", " ")
    for candidate in (meta.get("name"), shorten(description, width=80, placeholder="…"), filename):
        if isinstance(candidate, str):
            name = " ".join(candidate.split())
            if name and name.casefold() not in {"…", "imported template", "reusable template", "template", "untitled"}:
                return name
    weeks = meta.get("estimated_weeks")
    return f"{weeks}-Week Training Program" if weeks else "Training Program"
