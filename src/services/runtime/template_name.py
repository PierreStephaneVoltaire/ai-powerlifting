from pathlib import PureWindowsPath


def imported_template_name(program_name, source_filename, import_id):
    filename = PureWindowsPath(source_filename or "").stem.replace("_", " ")
    for candidate in (program_name, filename):
        if isinstance(candidate, str):
            name = " ".join(candidate.split())
            if name and name.casefold() not in {"imported template", "reusable template", "template", "untitled"}:
                return name
    return f"Training program {import_id}"
