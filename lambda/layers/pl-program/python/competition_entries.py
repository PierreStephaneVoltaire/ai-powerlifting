import copy
import os

import boto3
from boto3.dynamodb.conditions import Key


def load_entries(pk: str) -> list[dict]:
    table = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1')).Table(os.getenv('POWERLIFTING_USER_COMPETITIONS_TABLE', 'if-powerlifting-user-competitions'))
    arguments = {'KeyConditionExpression': Key('pk').eq(pk) & Key('sk').begins_with('COMP#'), 'ConsistentRead': True}
    entries = []
    while True:
        response = table.query(**arguments)
        entries.extend(response.get('Items', []))
        if not response.get('LastEvaluatedKey'):
            return entries
        arguments['ExclusiveStartKey'] = response['LastEvaluatedKey']


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


def with_competition_entries(program: dict, pk: str, entries: list[dict] | None = None) -> dict:
    return {**program, 'competitions': merge_entries(program.get('competitions') or [], load_entries(pk) if entries is None else entries)}
