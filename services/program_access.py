import re

from .access import META_DOMAINS, PROGRAM_FIELDS, permits
from .dispatch import OperationError


def authorize_program_change(operation: str, arguments: dict, context: dict) -> None:
    required = set()
    fields = set()
    if operation in ('program_update_meta_field', 'health_update_meta'):
        if isinstance(arguments.get('updates'), dict):
            fields.update(arguments['updates'])
        else:
            fields.add(arguments.get('field'))
    elif operation == 'health_new_version':
        for patch in arguments.get('patches') or []:
            if not isinstance(patch, dict) or not isinstance(patch.get('path'), str):
                raise OperationError(400, 'invalid_patch', 'Each patch requires a path and value')
            path = re.split(r'[.\[]', patch['path'])
            if path[0] == 'meta':
                if len(path) > 1:
                    fields.add(path[1])
                elif isinstance(patch.get('value'), dict):
                    fields.update(patch['value'])
            elif path[0] in PROGRAM_FIELDS:
                required.add(PROGRAM_FIELDS[path[0]])
            else:
                raise OperationError(400, 'invalid_patch', 'This Program field cannot be patched')
    elif operation in ('template_apply', 'template_apply_confirm'):
        for permission in ('program:read', 'performance:read', 'glossary:read'):
            if not permits(context, permission):
                raise OperationError(403, 'forbidden', f'{permission} permission required')
        if operation == 'template_apply_confirm':
            required.update(('program', 'sessions'))
            if arguments.get('target', 'new_block') == 'new_block':
                required.add('performance')
    elif operation == 'block_transition' and arguments.get('action') != 'rename':
        required.add('sessions')
        if arguments.get('action') in ('start_next', 'complete_and_start'):
            required.add('performance')
    elif operation == 'health_setup_initialize':
        required.update(('sessions', 'performance'))
        if arguments.get('mode') == 'template' and not permits(context, 'templates:read'):
            raise OperationError(403, 'forbidden', 'templates:read permission required')
    for domain, names in META_DOMAINS.items():
        if fields.intersection(names):
            required.add(domain)
    for domain in sorted(required):
        if not permits(context, f'{domain}:write'):
            raise OperationError(403, 'forbidden', f'{domain}:write permission required')
    if 'competition' in required and context.get('competition_scope', {}).get('write') is not None:
        raise OperationError(403, 'forbidden', 'Edit tied Competition Entries through their individual operations')
