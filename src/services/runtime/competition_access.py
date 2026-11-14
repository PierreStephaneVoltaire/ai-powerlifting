from .dispatch import OperationError


def matches(entry: dict, identifiers: list[str]) -> bool:
    keys = {str(entry.get(key) or '') for key in ('master_id', 'competition_id', 'id', 'sk')}
    keys.update(key.removeprefix('COMP#') for key in list(keys))
    return bool(keys.intersection(str(identifier).removeprefix('COMP#') for identifier in identifiers))


def authorize_entry(operation: str, arguments: dict, permission: str | None, context: dict) -> None:
    if not operation.startswith('health_') or 'competition' not in operation:
        return
    action = 'write' if permission == 'competition:write' else 'read'
    identifiers = context.get('competition_scope', {}).get(action)
    if identifiers is None:
        return
    if operation == 'health_list_competitions' and action == 'read':
        return
    if not matches(arguments.get('competition') or arguments, identifiers):
        raise OperationError(403, 'forbidden', 'This Competition Entry is outside the current grant')


def visible_entries(entries: list[dict], context: dict) -> list[dict]:
    identifiers = context.get('competition_scope', {}).get('read')
    return entries if identifiers is None else [entry for entry in entries if matches(entry, identifiers)]
