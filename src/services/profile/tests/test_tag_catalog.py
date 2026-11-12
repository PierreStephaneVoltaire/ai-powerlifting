import copy

import pytest
from botocore.exceptions import ClientError

from services.runtime import tag_catalog as tags
from services.runtime.dispatch import OperationError


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
        if key in self.items and kwargs.get('ConditionExpression') == 'attribute_not_exists(pk)':
            raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'PutItem')
        self.items[key] = copy.deepcopy(Item)

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        current = self.items[(Key['pk'], Key.get('sk'))]
        assert 'ConditionExpression' not in kwargs
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
    assert next(tag for tag in result['tags'] if tag['tag'] == 'Long Arms')['approved'] is False
    tags.select({**own, 'tag': 'long arms'})
    assert len(catalog.items) == 1
    assert tags.handler({}, None)['tags'] == []
    assert tags.handler(own, None)['tags'][0]['status'] == 'pending'
    decision = {'tag': 'long arms'}
    with pytest.raises(OperationError, match='operator'):
        tags.decide({**own, **decision})
    operator = {**own, '_person_pk': 'operator-person', '_access': {'permissions': ['operator:write']}}
    approved = tags.decide({**operator, **decision})
    assert tags.decide({**operator, **decision}) == approved
    assert tags.handler({}, None)['tags'] == [{'tag': 'Long Arms', 'status': 'approved'}]
    assert tags.selected_tags(result['tags'])[1]['approved'] is True
    tags.decide({**operator, **decision, 'decision': 'rejected'})
    assert tags.handler({}, None)['tags'] == []
    assert all(not tag['approved'] for tag in tags.selected_tags(result['tags']))
    with pytest.raises(OperationError, match='own profile'):
        tags.select({**own, 'tag': 'another', 'target_nickname': 'somebody-else'})


def test_tags_allow_any_text_up_to_fifty_characters():
    assert tags.normalize_tag("  doesn't   wash knee sleeves ") == "doesn't wash knee sleeves"
    assert tags.normalize_tag(' ＳＱＵＡＴ   Specialist ') == 'SQUAT Specialist'
    assert tags.normalize_tag('x' * 50) == 'x' * 50
    for bad in ('x' * 51, '   ', 42):
        with pytest.raises(ValueError):
            tags.normalize_tag(bad)
    assert len(tags.selected_tags(['same', ' Same ', *[f'tag {index}' for index in range(30)]], {})) == 20
    assert [tag['tag'] for tag in tags.selected_tags(['Knee sleeves', 'knee sleeves'], {})] == ['Knee sleeves']
    assert tags.canonical_tag('KNEE SLEEVES', {'knee sleeves': {}}) == 'knee sleeves'


def test_profile_and_settings_readers_keep_sentence_tags():
    from services.profile.profile_get.core import _normalize_tag as profile_tag
    from services.profile.settings_get.core import _normalize_tag as settings_tag
    from services.profile.settings_update_profile.core import _normalize_tag as update_tag
    for normalize in (profile_tag, settings_tag, update_tag):
        assert normalize("doesn't wash knee sleeves") == "doesn't wash knee sleeves"
        assert normalize('x' * 51) is None
