import os
import re
import unicodedata
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .access_store import database, pages
from .dispatch import OperationError


MAX_TAG_LENGTH = 50


def normalize_tag(value):
    if not isinstance(value, str):
        raise ValueError('Tag must be text')
    tag = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip()
    if not tag or len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f'Tags must be 1–{MAX_TAG_LENGTH} characters')
    return tag


def tag_key(tag):
    return tag.casefold()


def canonical_tag(name, vocabulary):
    return next((existing for existing in vocabulary if tag_key(existing) == tag_key(name)), name)


def table():
    return database().Table(os.getenv('POWERLIFTING_TAGS_TABLE', 'if-powerlifting-tags'))


def catalog():
    return {item['tag']: item for item in pages(table(), 'query', KeyConditionExpression=Key('pk').eq('Catalog'), ConsistentRead=True)}


def selected_tags(raw, vocabulary=None):
    names = []
    for item in raw if isinstance(raw, list) else []:
        try:
            name = normalize_tag(item.get('tag') if isinstance(item, dict) else item)
        except ValueError:
            continue
        if tag_key(name) not in {tag_key(existing) for existing in names}:
            names.append(name)
    vocabulary = catalog() if names and vocabulary is None else (vocabulary or {})
    return [{'tag': name, 'approved': vocabulary.get(name, {}).get('status') == 'approved', 'status': vocabulary.get(name, {}).get('status', 'pending'), 'proposed_by': ''} for name in names[:20]]


def handler(args, _context):
    operator = 'operator:write' in args.get('_access', {}).get('permissions', [])
    include_pending = args.get('include_pending') is True
    if include_pending and not operator:
        raise OperationError(403, 'forbidden', 'Only the operator may review the catalog')
    personal = set()
    person = args.get('_access', {}).get('settings_pk')
    if person:
        owner = database().Table(os.getenv('IF_USER_TABLE', 'if-user')).get_item(Key={'pk': person}, ConsistentRead=True).get('Item') or {}
        personal = {item['tag'] for item in selected_tags(owner.get('tags'), {})}
    return {'tags': [{'tag': row['tag'], 'status': row['status']} for row in sorted(catalog().values(), key=lambda row: row['tag']) if include_pending or row['status'] == 'approved' or row['tag'] in personal]}


def decide(args):
    if 'operator:write' not in args.get('_access', {}).get('permissions', []):
        raise OperationError(403, 'forbidden', 'Only the operator may approve vocabulary')
    name = canonical_tag(normalize_tag(args['tag']), catalog())
    decision = args.get('decision', 'approved')
    if decision not in ('approved', 'rejected'):
        raise ValueError('Decision must be approved or rejected')
    key = {'pk': 'Catalog', 'sk': 'Tag#' + name}
    store = table()
    current = store.get_item(Key=key, ConsistentRead=True).get('Item') or {}
    store.put_item(Item={**current, **key, 'tag': name, 'status': decision, 'decided_by': args['_person_pk'], 'updated_at': datetime.now(timezone.utc).isoformat()})
    return {'tag': name, 'status': decision}


def select(args, remove=False):
    from importlib import import_module
    normalize = import_module('services.profile.settings_get.core')._normalize_settings
    name = normalize_tag(args['tag'])
    person = args.get('_access', {}).get('settings_pk')
    if not person or person != args.get('pk'):
        raise OperationError(403, 'forbidden', 'Authenticated profile owner required')
    users = database().Table(os.getenv('IF_USER_TABLE', 'if-user'))
    current = users.get_item(Key={'pk': person}, ConsistentRead=True).get('Item')
    if not current:
        raise ValueError('Profile not found')
    if args.get('target_nickname') and args['target_nickname'] != current.get('nickname'):
        raise OperationError(403, 'forbidden', 'Tags can only be selected for your own profile')
    vocabulary = catalog()
    name = canonical_tag(name, vocabulary)
    selected = selected_tags(current.get('tags'), vocabulary)
    if not remove and tag_key(name) not in {tag_key(tag['tag']) for tag in selected} and len(selected) >= 20:
        raise ValueError('A profile can have at most twenty tags')
    if not remove and name not in vocabulary:
        pending = {'pk': 'Catalog', 'sk': 'Tag#' + name, 'tag': name, 'status': 'pending', 'requested_by': person, 'created_at': datetime.now(timezone.utc).isoformat()}
        try:
            table().put_item(Item=pending, ConditionExpression='attribute_not_exists(pk)')
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
    tags = [tag for tag in selected if tag_key(tag['tag']) != tag_key(name)]
    if not remove:
        tags.append({'tag': name})
    values = {':tags': tags, ':now': datetime.now(timezone.utc).isoformat()}
    users.update_item(Key={'pk': person}, UpdateExpression='SET tags = :tags, updated_at = :now', ExpressionAttributeValues=values)
    return normalize({**current, 'tags': selected_tags(tags), 'updated_at': values[':now']})
