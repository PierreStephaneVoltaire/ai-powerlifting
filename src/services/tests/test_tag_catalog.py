import copy

import pytest
from botocore.exceptions import ClientError

from services import tag_catalog as tags
from services.dispatch import OperationError


class Table:
    def __init__(self, items=()):
        self.items = {(item['pk'], item.get('sk')): copy.deepcopy(item) for item in items}

    def get_item(self, Key, **kwargs):
        item = self.items.get((Key['pk'], Key.get('sk')))
        return {'Item': copy.deepcopy(item)} if item else {}

    def query(self, **kwargs):
        return {'Items': list(self.items.values())}

    def put_item(self, Item, **kwargs):
        key = (Item['pk'], Item.get('sk'))
        current = self.items.get(key)
        expected = kwargs.get('ExpressionAttributeValues', {}).get(':revision')
        if current and (expected is None or current.get('revision') != expected):
            raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'PutItem')
        self.items[key] = copy.deepcopy(Item)

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        current = self.items[(Key['pk'], Key.get('sk'))]
        assert current.get('tags') == ExpressionAttributeValues.get(':previous')
        current['tags'] = copy.deepcopy(ExpressionAttributeValues[':tags'])


def test_global_approval_is_operator_only_and_legacy_flags_never_publish(monkeypatch):
    users = Table([{'pk': 'person-a', 'nickname': 'athlete-a', 'tags': [{'tag': 'legacy', 'approved': True}]}])
    catalog = Table()
    class Database:
        def Table(self, name):
            return users if name == 'if-user' else catalog
    monkeypatch.setattr(tags, 'database', Database)
    own = {'pk': 'person-a', '_person_pk': 'person-a', '_access': {'settings_pk': 'person-a', 'permissions': ['settings:write']}}
    assert tags.selected_tags(users.items[('person-a', None)]['tags'])[0]['approved'] is False
    result = tags.select({**own, 'tag': '  Long   Arms  ', 'approved': True})
    assert next(tag for tag in result['tags'] if tag['tag'] == 'long-arms')['approved'] is False
    tags.select({**own, 'tag': 'long-arms'})
    assert len(catalog.items) == 1
    assert tags.handler({}, None)['tags'] == []
    assert tags.handler(own, None)['tags'][0]['status'] == 'pending'
    decision = {'tag': 'long-arms', 'expected_revision': 1, 'idempotency_key': 'approve-1'}
    with pytest.raises(OperationError, match='operator'):
        tags.decide({**own, **decision})
    operator = {**own, '_person_pk': 'operator-person', '_access': {'permissions': ['operator:write']}}
    approved = tags.decide({**operator, **decision})
    assert tags.decide({**operator, **decision}) == approved
    assert tags.handler({}, None)['tags'] == [{'tag': 'long-arms', 'status': 'approved', 'revision': 2}]
    assert tags.selected_tags(result['tags'])[1]['approved'] is True
    with pytest.raises(OperationError, match='changed'):
        tags.decide({**operator, **decision, 'idempotency_key': 'race', 'decision': 'rejected'})
    tags.decide({**operator, **decision, 'expected_revision': 2, 'idempotency_key': 'reject-2', 'decision': 'rejected'})
    assert tags.handler({}, None)['tags'] == []
    assert all(not tag['approved'] for tag in tags.selected_tags(result['tags']))
    with pytest.raises(OperationError, match='own profile'):
        tags.select({**own, 'tag': 'another', 'target_nickname': 'somebody-else'})


def test_tag_limits_and_normalization():
    assert tags.normalize_tag(' ＳＱＵＡＴ   Specialist ') == 'squat-specialist'
    with pytest.raises(ValueError):
        tags.normalize_tag('x' * 31)
    assert len(tags.selected_tags(['same', ' Same ', *[f'tag-{index}' for index in range(30)]], {})) == 20
