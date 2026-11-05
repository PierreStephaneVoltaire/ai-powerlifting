import copy
import os
from datetime import date

from services.lib.aws import dynamodb_resource
from boto3.dynamodb.conditions import Key


ENTRIES_BY_DATE_INDEX = 'entries-by-date'


def participation_date(entry: dict) -> str | None:
    status = entry.get('user_status') or entry.get('status') or 'available'
    if status == 'available':
        return None
    return entry.get('start_date') or entry.get('date') or None


def _query_all(table, arguments: dict) -> list[dict]:
    entries = []
    while True:
        response = table.query(**arguments)
        entries.extend(response.get('Items', []))
        if not response.get('LastEvaluatedKey'):
            return entries
        arguments['ExclusiveStartKey'] = response['LastEvaluatedKey']


def load_entries(pk: str, start: str | None = None, end: str | None = None, table=None) -> list[dict]:
    if table is None:
        table = dynamodb_resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1')).Table(os.getenv('POWERLIFTING_USER_COMPETITIONS_TABLE', 'if-powerlifting-user-competitions'))
    condition = Key('pk').eq(pk)
    if start and end:
        condition &= Key('entry_date').between(start, end)
    elif start:
        condition &= Key('entry_date').gte(start)
    elif end:
        condition &= Key('entry_date').lte(end)
    return _query_all(table, {'IndexName': ENTRIES_BY_DATE_INDEX, 'KeyConditionExpression': condition})


def normalize_entries(entries: list[dict]) -> list[dict]:
    normalized = []
    for entry in entries:
        status = entry.get('user_status') or entry.get('status')
        if status == 'available' or not status:
            continue
        current = copy.deepcopy(entry)
        current.pop('pk', None)
        current.pop('sk', None)
        current.pop('test_seed_source_pk', None)
        current['master_id'] = entry.get('master_id') or str(entry.get('sk', '')).removeprefix('COMP#')
        current['date'] = entry.get('start_date') or entry.get('date')
        current['status'] = status
        current['federation'] = entry.get('federation_label') or entry.get('federation')
        current['body_weight_kg'] = entry.get('body_weight_kg')
        current['units'] = entry.get('units') or 'kg'
        normalized.append(current)
    return sorted(normalized, key=lambda entry: (str(entry.get('date') or ''), str(entry.get('master_id') or '')))


def with_competition_entries(program: dict, pk: str, entries: list[dict] | None = None, start: str | None = None, end: str | None = None) -> dict:
    return {**program, 'competitions': normalize_entries(load_entries(pk, start, end) if entries is None else entries)}


def next_competition(competitions: list[dict], today: date | None = None) -> dict | None:
    today = today or date.today()
    upcoming = []
    for entry in competitions:
        if (entry.get('status') or entry.get('user_status')) != 'confirmed':
            continue
        try:
            when = date.fromisoformat(str(entry.get('date') or entry.get('start_date') or '')[:10])
        except ValueError:
            continue
        if when > today:
            upcoming.append((when, entry))
    return min(upcoming, key=lambda item: item[0])[1] if upcoming else None
