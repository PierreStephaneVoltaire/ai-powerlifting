import os
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Attr, Key

from .access import evaluate_facts


@lru_cache(maxsize=1)
def database():
    return boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1'))


def pages(table, method: str, **arguments):
    while True:
        response = getattr(table, method)(**arguments)
        yield from response.get('Items', [])
        if not response.get('LastEvaluatedKey'):
            return
        arguments['ExclusiveStartKey'] = response['LastEvaluatedKey']


def person_record(identifier: str) -> dict | None:
    if not identifier:
        return None
    table = database().Table(os.getenv('IF_USER_TABLE', 'if-user'))
    direct = table.get_item(Key={'pk': identifier}, ConsistentRead=True).get('Item')
    if direct:
        return direct
    matches = [item for item in pages(table, 'scan', FilterExpression=Attr('mapped_pk').eq(identifier), ConsistentRead=True)
               if not str(item.get('pk', '')).startswith('Identity#')]
    return matches[0] if len(matches) == 1 else None


def current_context(person: str, athlete: str) -> dict:
    actor = person_record(person)
    owner = actor if actor and athlete in (actor.get('pk'), actor.get('mapped_pk')) else person_record(athlete)
    grants = []
    dates = {}
    if actor and owner and (actor.get('mapped_pk') or actor['pk']) != athlete:
        table = database().Table(os.getenv('IF_POWERLIFTING_REQUESTS_TABLE', 'if-powerlifting-requests'))
        grants = list(pages(table, 'query', KeyConditionExpression=Key('pk').eq(f'Grant#{athlete}'), ConsistentRead=True))
        competitions = database().Table(os.getenv('POWERLIFTING_USER_COMPETITIONS_TABLE', 'if-powerlifting-user-competitions'))
        for item in pages(competitions, 'query', KeyConditionExpression=Key('pk').eq(athlete) & Key('sk').begins_with('COMP#'), ConsistentRead=True):
            value = item.get('date') or item.get('competition_date') or item.get('start_date')
            if isinstance(value, str):
                for key in (item['sk'], item['sk'][5:], item.get('competition_id'), item.get('master_id'), item.get('id')):
                    if key:
                        dates[key] = value
    context = evaluate_facts(person, athlete, owner, actor, grants, dates)
    if owner and 'profile:read' in context['permissions']:
        context['athlete_display_name'] = owner.get('display_name') or owner.get('nickname') or athlete
    return context


def handler(event, context):
    return event['_access']
