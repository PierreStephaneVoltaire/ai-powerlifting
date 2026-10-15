import copy
import os

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


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
        table = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1')).Table(os.getenv('POWERLIFTING_USER_COMPETITIONS_TABLE', 'if-powerlifting-user-competitions'))
    condition = Key('pk').eq(pk)
    if start and end:
        condition &= Key('entry_date').between(start, end)
    elif start:
        condition &= Key('entry_date').gte(start)
    elif end:
        condition &= Key('entry_date').lte(end)
    try:
        return _query_all(table, {'IndexName': ENTRIES_BY_DATE_INDEX, 'KeyConditionExpression': condition})
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') not in {'ValidationException', 'ResourceNotFoundException'}:
            raise
    entries = _query_all(table, {'KeyConditionExpression': Key('pk').eq(pk) & Key('sk').begins_with('COMP#'), 'ConsistentRead': True})
    return [entry for entry in entries if (date := participation_date(entry)) and (not start or date >= start) and (not end or date <= end)]


def merge_entries(legacy: list[dict], entries: list[dict]) -> list[dict]:
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
    identifiers = {entry['master_id'] for entry in normalized if entry['master_id']}
    dated_names = {(entry['date'], str(entry.get('name') or '').strip().casefold()) for entry in normalized}
    retained = [copy.deepcopy(entry) for entry in legacy if entry.get('master_id') not in identifiers and (entry.get('date'), str(entry.get('name') or '').strip().casefold()) not in dated_names]
    return sorted([*retained, *normalized], key=lambda entry: (str(entry.get('date') or ''), str(entry.get('master_id') or entry.get('name') or '')))


def with_competition_entries(program: dict, pk: str, entries: list[dict] | None = None, start: str | None = None, end: str | None = None) -> dict:
    return {**program, 'competitions': merge_entries(program.get('competitions') or [], load_entries(pk, start, end) if entries is None else entries)}
