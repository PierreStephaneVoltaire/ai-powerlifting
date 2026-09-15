import asyncio
import importlib
import json
from types import SimpleNamespace

import boto3
import pytest


def test_basics_atomically_store_dated_estimated_1rms_and_retry_without_duplicates(monkeypatch):
    core = importlib.import_module('lambda.pod_user.handlers.settings_update_athlete_basics.core')
    person = {'pk': 'person-a', 'mapped_pk': 'athlete-a', 'roles': ['athlete'], 'updated_at': 'before'}
    history = {}
    transactions = []

    def transact(TransactItems):
        transactions.append(TransactItems)
        update = TransactItems[0]['Update']
        assert update['Key'] == {'pk': 'person-a'}
        assert update['ExpressionAttributeValues'][':previous'] == person['updated_at']
        for alias, name in update['ExpressionAttributeNames'].items():
            if alias.startswith('#f'):
                person[name] = update['ExpressionAttributeValues'][':v' + alias[2:]]
        if len(TransactItems) == 2:
            seed = TransactItems[1]['Update']
            assert seed['Key'] == {'pk': 'athlete-a', 'sk': 'max_history#current'}
            values = seed['ExpressionAttributeValues']
            history.setdefault('entries', []).extend(values[':entry'])
            history.setdefault('basics_entry_ids', set()).update(values[':ids'])

    user_table = SimpleNamespace(name='if-user', get_item=lambda **kwargs: {'Item': dict(person)}, meta=SimpleNamespace(client=SimpleNamespace(transact_write_items=transact)))
    health_table = SimpleNamespace(name='if-health', get_item=lambda **kwargs: {'Item': history})
    monkeypatch.setattr(core, '_get_table', lambda: user_table)
    real_resource = boto3.resource
    monkeypatch.setattr(core.boto3, 'resource', lambda *args, **kwargs: SimpleNamespace(Table=lambda name: health_table))
    args = {'username': 'person-a', 'input': {'sex': 'female', 'country': 'ca', 'bodyweight_kg': 63.5, 'training_maxes': {'squat_kg': 145.5, 'bench_kg': 82.5, 'deadlift_kg': 180}, 'maxes_date': '2026-09-01', 'training_maxes_estimated': {'bench': True}}}
    result = asyncio.run(core.settings_update_athlete_basics(args))
    assert result['athlete_basics_complete'] and result['ranking_country'] == 'CA'
    assert result['maxes_date'] == '2026-09-01'
    assert result['training_maxes_estimated'] == {'squat': False, 'bench': True, 'deadlift': False}
    asyncio.run(core.settings_update_athlete_basics(args))
    assert len(history['entries']) == 1 and len(transactions[-1]) == 1

    client = real_resource('dynamodb', region_name='ca-central-1', aws_access_key_id='test', aws_secret_access_key='test').meta.client
    class Captured(Exception):
        pass
    def capture(params, **kwargs):
        wire = json.loads(params['body'])['TransactItems']
        assert wire[0]['Update']['Key']['pk'] == {'S': 'person-a'}
        entry = wire[1]['Update']['ExpressionAttributeValues'][':entry']['L'][0]['M']
        assert entry['squat_kg'] == {'N': '145.5'}
        assert entry['estimated']['M']['bench'] == {'BOOL': True}
        raise Captured()
    client.meta.events.register('before-call.dynamodb.TransactWriteItems', capture)
    with pytest.raises(Captured):
        client.transact_write_items(TransactItems=transactions[0])
    person['roles'] = ['coach', 'handler']
    with pytest.raises(ValueError, match='Athlete role'):
        asyncio.run(core.settings_update_athlete_basics(args))


def test_non_athlete_profile_onboarding_finishes_without_training_basics():
    module = importlib.import_module('lambda.pod_user.handlers._shared.settings_normalize')
    settings = {'roles': ['coach', 'handler'], 'active_role': 'handler', 'profile_complete': True}
    assert module.derive_onboarding_status(settings)['next_step'] == 'done'
    settings['roles'].append('athlete')
    assert module.derive_onboarding_status(settings)['next_step'] == 'athlete_basics'


def test_legacy_onboarding_prefills_only_owned_known_values(monkeypatch):
    from decimal import Decimal
    from services import access_store
    core = importlib.import_module('lambda.pod_user.handlers.onboarding_status.core')
    reads = []
    def get_item(Key, **kwargs):
        reads.append(Key)
        assert kwargs['ConsistentRead']
        assert Key['pk'] == 'own-athlete'
        if Key['sk'] == 'program#current':
            return {'Item': {'ref_sk': 'program#v001'}}
        return {'Item': {'meta': {'current_body_weight_kg': Decimal('73.5'), 'manual_maxes': {'squat': Decimal('150'), 'bench': 90, 'deadlift': 180}}}}
    monkeypatch.setattr(access_store, 'database', lambda: SimpleNamespace(Table=lambda _: SimpleNamespace(get_item=get_item)))
    async def settings(_args):
        return {'pk': 'own-person', 'mapped_pk': 'own-athlete', 'roles': [], 'sex': None}
    monkeypatch.setattr(core, 'settings_get', settings)
    result = asyncio.run(core.onboarding_status({'pk': 'own-person', '_access': {'athlete_pk': 'selected-delegate'}}))
    assert result['prefill'] == {'bodyweight_kg': 73.5, 'training_maxes': {'squat_kg': 150, 'bench_kg': 90, 'deadlift_kg': 180}}
    assert result['next_step'] == 'role' and not result['has_athlete_basics']
    assert len(reads) == 2 and 'sex' not in result['prefill']
