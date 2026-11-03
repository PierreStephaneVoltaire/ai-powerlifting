import asyncio
from types import SimpleNamespace

from botocore.exceptions import ClientError
import pytest


class Table:
    name = "if-user"

    def __init__(self, items=()):
        self.items = {item["pk"]: item for item in items}
        self.meta = SimpleNamespace(client=SimpleNamespace(transact_write_items=self.transact))

    def get_item(self, Key, ConsistentRead=False):
        assert ConsistentRead
        return {"Item": self.items[Key["pk"]]} if Key["pk"] in self.items else {}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}

    def put_item(self, Item, ConditionExpression):
        assert ConditionExpression == 'attribute_not_exists(pk)'
        if Item['pk'] in self.items:
            raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'PutItem')
        self.items[Item['pk']] = Item

    def transact(self, TransactItems):
        items = []
        for operation in TransactItems:
            if 'Update' in operation:
                update = operation['Update']
                pk = update['Key']['pk']
                item = dict(self.items[pk])
                for field in ('issuer', 'provider', 'sub'):
                    item.setdefault('identity_' + field, update['ExpressionAttributeValues'][':' + field])
                item.setdefault('roles', update['ExpressionAttributeValues'][':roles'])
                items.append(item)
                continue
            assert operation['Put']['ConditionExpression'] == 'attribute_not_exists(pk)'
            item = dict(operation["Put"]["Item"])
            if item['pk'] in self.items:
                raise ClientError({'Error': {'Code': 'TransactionCanceledException'}}, 'TransactWriteItems')
            items.append(item)
        for item in items:
            self.items[item["pk"]] = item


def resolve(monkeypatch, table, **args):
    module = __import__("services.handlers.user.identity_resolve.core", fromlist=["identity_resolve"])
    monkeypatch.setattr(module, "_get_table", lambda: table)
    return asyncio.run(module.identity_resolve(args))


def test_missing_identity_isolated_from_operator_and_name_collisions(monkeypatch):
    table = Table([{"pk": "operator", "username": "operator", "display_name": "Same Name", "email": "same@example.com"}])
    result = resolve(monkeypatch, table, issuer="issuer-a", provider="authentik", sub="subject-a", display_name="Same Name")
    assert result["created"] is True
    assert result["settings"]["pk"] != "operator"
    assert result["settings"]["roles"] == []
    assert result["settings"]["identity_issuer"] == "issuer-a"


def test_same_subject_retries_resolve_once(monkeypatch):
    table = Table()
    first = resolve(monkeypatch, table, issuer="issuer-a", provider="discord", sub="42", display_name="Lifter")
    second = resolve(monkeypatch, table, issuer="issuer-a", provider="discord", sub="42", display_name="Other")
    assert first["created"] is True
    assert second["created"] is False
    assert second["settings"]["pk"] == first["settings"]["pk"]


def test_same_sub_different_issuer_cannot_take_over(monkeypatch):
    table = Table()
    first = resolve(monkeypatch, table, issuer="issuer-a", provider="authentik", sub="same", display_name="One")
    second = resolve(monkeypatch, table, issuer="issuer-b", provider="authentik", sub="same", display_name="Two")
    assert second["created"] is True
    assert second["settings"]["pk"] != first["settings"]["pk"]


def test_existing_operator_explicit_identity_is_preserved(monkeypatch):
    table = Table([{"pk": "operator", "username": "operator", "identity_issuer": "issuer-a", "identity_sub": "op", "roles": []}])
    result = resolve(monkeypatch, table, issuer="issuer-a", provider="authentik", sub="op", display_name="Changed")
    assert result["created"] is False
    assert result["settings"]["pk"] == "operator"
    assert len(table.items) == 2
    monkeypatch.setattr(table, 'scan', lambda **kwargs: pytest.fail('Resolved identity must use its durable pointer'))
    assert resolve(monkeypatch, table, issuer='issuer-a', provider='authentik', sub='op')['settings']['pk'] == 'operator'


def test_ambiguous_subject_never_selects_first_person(monkeypatch):
    table = Table([{'pk': pk, 'identity_issuer': 'issuer-a', 'identity_sub': 'same'} for pk in ('person-a', 'person-b')])
    with pytest.raises(ValueError, match='multiple Persons'):
        resolve(monkeypatch, table, issuer='issuer-a', provider='authentik', sub='same')
    assert len(table.items) == 2


def test_verified_discord_subject_preserves_legacy_operator_partition(monkeypatch):
    table = Table([{'pk': 'legacy_username', 'mapped_pk': 'operator', 'discord_id': '1234', 'display_name': 'Old Name'}])
    result = resolve(monkeypatch, table, issuer='https://auth.example/application/o/app/', provider='authentik', sub='oidc-sub', discord_subjects=['1234'], display_name='Changed Name')
    assert result['created'] is False
    assert result['settings']['pk'] == 'legacy_username'
    assert result['settings']['mapped_pk'] == 'operator'
    assert result['settings']['roles'] == ['athlete']
    assert result['settings']['identity_sub'] == 'oidc-sub'


def test_unverified_discord_name_cannot_link_legacy_account(monkeypatch):
    table = Table([{'pk': 'legacy_username', 'mapped_pk': 'operator', 'discord_id': '1234'}])
    result = resolve(monkeypatch, table, issuer='https://auth.example/application/o/app/', provider='authentik', sub='1234', display_name='legacy_username')
    assert result['created'] is True
    assert result['settings']['mapped_pk'] != 'operator'


def test_racing_first_logins_return_winning_person(monkeypatch):
    table = Table()
    transact = table.transact
    racing = False
    winner = None

    def race(TransactItems):
        nonlocal racing, winner
        if not racing:
            racing = True
            winner = resolve(monkeypatch, table, issuer='issuer-a', provider='authentik', sub='same')
        transact(TransactItems)

    table.meta.client.transact_write_items = race
    result = resolve(monkeypatch, table, issuer='issuer-a', provider='authentik', sub='same')
    assert result['created'] is False
    assert result['settings']['pk'] == winner['settings']['pk']
    assert len(table.items) == 2


@pytest.mark.parametrize('legacy', [False, True])
def test_identity_transactions_encode_scalar_keys_with_real_boto3(monkeypatch, legacy):
    import boto3
    import json
    table = Table([{'pk': 'legacy', 'discord_id': '42'}] if legacy else [])
    client = boto3.resource('dynamodb', region_name='ca-central-1', aws_access_key_id='test', aws_secret_access_key='test').meta.client
    table.meta.client = client
    class Captured(Exception):
        pass
    def capture(params, **kwargs):
        for operation in json.loads(params['body'])['TransactItems']:
            item = operation.get('Put', {}).get('Item') or operation['Update']['Key']
            assert set(item['pk']) == {'S'}
        raise Captured()
    client.meta.events.register('before-call.dynamodb.TransactWriteItems', capture)
    with pytest.raises(Captured):
        resolve(monkeypatch, table, issuer='issuer-a', provider='authentik', sub='subject', discord_subjects=['42'])
