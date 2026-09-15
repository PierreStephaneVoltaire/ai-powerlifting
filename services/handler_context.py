import asyncio
import importlib
import os
from datetime import date

from boto3.dynamodb.conditions import Key

from .access_store import database, pages, person_record
from .dispatch import OperationError
from .profile_views import visible_profile
from .publication import program_view
from .tag_catalog import catalog
from .competition_access import visible_entries


def handler(args, _context):
    owner = person_record(args['pk'])
    access = args['_access']
    profile = visible_profile(owner, args['_person_pk'], catalog(), details=True) if owner else None
    if not profile:
        raise OperationError(404, 'not_found', 'Athlete not found')
    permissions = set(access['permissions'])
    table = database().Table(os.getenv('POWERLIFTING_USER_COMPETITIONS_TABLE', 'if-powerlifting-user-competitions'))
    entries = list(pages(table, 'query', KeyConditionExpression=Key('pk').eq(args['pk']) & Key('sk').begins_with('COMP#'), ConsistentRead=True))
    all_entries = entries
    entries = visible_entries(entries, access)
    from program_store import ProgramNotFoundError
    from program_tool_helpers import get_store
    try:
        program = asyncio.run(get_store(args).get_program())
    except ProgramNotFoundError:
        program = {}
    from competition_entries import with_competition_entries
    program = with_competition_entries(program, args['pk'], all_entries)
    filtered = program_view(program, access)
    meta = filtered.get('meta') or {}
    current_id = meta.get('current_block_id')
    block = next((block for block in meta.get('blocks', []) if block.get('id') == current_id), None)
    if not block and program:
        block = {'id': current_id or 'current', 'name': 'Current Block', 'status': 'active'}
    sessions = [session for session in program.get('sessions', []) if session.get('block', 'current') == 'current']
    sessions.sort(key=lambda session: str(session.get('date', '')))
    today = date.today().isoformat()
    nearest = next((session for session in sessions if str(session.get('date', '')) >= today), sessions[-1] if sessions else {})
    phase = nearest.get('phase')
    analytics = importlib.import_module('lambda.get_analysis_markdown.analytics')
    comp_maxes = analytics._estimate_maxes_from_comps(program.get('competitions', []), reference_date=date.today())
    session_maxes = analytics._estimate_maxes_from_sessions(program.get('sessions', []), reference_date=date.today())
    maxes = analytics._analysis_current_maxes_out(comp_maxes or session_maxes, comp_maxes, session_maxes)
    plain = importlib.import_module('lambda.pod_user.handlers.settings_get.core')._sanitize_decimals
    return plain({'profile': profile, 'block': block if 'program:read' in permissions else None, 'phase': phase if 'program:read' in permissions else None, 'estimated_maxes': maxes if 'performance:read' in permissions else {}, 'competitions': [{key: value for key, value in entry.items() if key not in ('pk', 'test_seed_source_pk')} for entry in entries] if 'competition:read' in permissions else [], 'notes': filtered.get('meta', {}).get('block_notes', []) if 'program:read' in permissions else []})
