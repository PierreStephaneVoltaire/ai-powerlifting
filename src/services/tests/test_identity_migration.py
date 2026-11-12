import importlib.util
from pathlib import Path
from types import SimpleNamespace

path = Path(__file__).resolve().parents[3] / 'scripts' / 'migrate_identity_pointers.py'
spec = importlib.util.spec_from_file_location('migrate_identity_pointers', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Table:
    name = 'users'

    def __init__(self, records):
        self.records = {item['pk']: item for item in records}
        self.meta = SimpleNamespace(client=SimpleNamespace(transact_write_items=self.transact))

    def scan(self, **kwargs):
        assert kwargs['ConsistentRead']
        return {'Items': list(self.records.values())}

    def transact(self, TransactItems):
        check, put = TransactItems
        source = self.records[check['ConditionCheck']['Key']['pk']]
        values = check['ConditionCheck']['ExpressionAttributeValues']
        assert all(source['identity_' + name] == values[':' + name] for name in ('issuer', 'sub', 'provider'))
        item = put['Put']['Item']
        assert item['pk'] not in self.records
        self.records[item['pk']] = item


def test_dry_run_apply_and_repeat_preserve_person():
    person = {'pk': 'legacy', 'mapped_pk': 'athlete', 'identity_issuer': 'issuer', 'identity_sub': 'subject', 'identity_provider': 'authentik'}
    table = Table([person])
    assert module.migrate(table)['planned'] == 1
    assert len(table.records) == 1
    assert module.migrate(table, apply=True)['created'] == 1
    assert table.records['legacy'] == person
    assert module.migrate(table, apply=True)['existing'] == 1


def test_duplicate_or_conflicting_subject_is_never_linked():
    person = {'pk': 'one', 'identity_issuer': 'issuer', 'identity_sub': 'subject', 'identity_provider': 'authentik'}
    duplicate = {**person, 'pk': 'two'}
    table = Table([person, duplicate])
    result = module.migrate(table, apply=True)
    assert result['conflicts'] and len(table.records) == 2
    key = module._identity_key('issuer', 'subject')
    table = Table([person, {'pk': key, 'mapped_pk': 'other'}])
    assert module.migrate(table, apply=True)['conflicts'] == [key]
