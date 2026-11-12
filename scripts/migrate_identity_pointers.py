import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from botocore.exceptions import ClientError
from services.profile.identity_resolve.core import _get_table, _identity_key, _scan


def migrate(table, apply=False):
    records = list(_scan(table, ConsistentRead=True))
    people = [item for item in records if not str(item.get('pk', '')).startswith('Identity#')]
    pointers = {item['pk']: item for item in records if str(item.get('pk', '')).startswith('Identity#')}
    identities = {}
    for person in people:
        issuer, subject = person.get('identity_issuer'), person.get('identity_sub')
        if not isinstance(issuer, str) or not issuer.strip() or not isinstance(subject, str) or not subject.strip():
            continue
        identity = (issuer.strip(), subject.strip())
        identities.setdefault(identity, []).append(person)
    result = {'created': 0, 'existing': 0, 'planned': 0, 'conflicts': []}
    for (issuer, subject), matches in identities.items():
        key = _identity_key(issuer, subject)
        pointer = pointers.get(key)
        if len(matches) != 1 or (pointer and (pointer.get('mapped_pk') != matches[0]['pk'] or pointer.get('identity_issuer') != issuer or pointer.get('identity_sub') != subject)):
            result['conflicts'].append(key)
            continue
        if pointer:
            result['existing'] += 1
            continue
        person = matches[0]
        provider = person.get('identity_provider')
        if provider not in ('authentik', 'discord'):
            result['conflicts'].append(key)
            continue
        if not apply:
            result['planned'] += 1
            continue
        try:
            table.meta.client.transact_write_items(TransactItems=[
                {'ConditionCheck': {'TableName': table.name, 'Key': {'pk': person['pk']},
                    'ConditionExpression': 'identity_issuer = :issuer AND identity_sub = :sub AND identity_provider = :provider',
                    'ExpressionAttributeValues': {':issuer': person['identity_issuer'], ':sub': person['identity_sub'], ':provider': provider}}},
                {'Put': {'TableName': table.name, 'Item': {'pk': key, 'mapped_pk': person['pk'], 'identity_issuer': issuer, 'identity_provider': provider, 'identity_sub': subject}, 'ConditionExpression': 'attribute_not_exists(pk)'}},
            ])
            result['created'] += 1
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'TransactionCanceledException':
                raise
            winner = table.get_item(Key={'pk': key}, ConsistentRead=True).get('Item')
            if winner and winner.get('mapped_pk') == person['pk'] and winner.get('identity_issuer') == issuer and winner.get('identity_sub') == subject:
                result['existing'] += 1
            else:
                result['conflicts'].append(key)
    return result


def main():
    parser = argparse.ArgumentParser(description='Create missing pointers for already verified identities; dry-run by default.')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = migrate(_get_table(), apply=args.apply)
    print(json.dumps(result, indent=2))
    return 1 if result['conflicts'] else 0


if __name__ == '__main__':
    sys.exit(main())
