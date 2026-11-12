import re

from botocore.exceptions import ClientError

DISCORD_ISSUER = 'https://discord.com'


def _linked_subjects(table, identity_key, person, subjects):
    linked = set()
    for subject in subjects:
        pointer = table.get_item(Key={'pk': identity_key(DISCORD_ISSUER, subject)}, ConsistentRead=True).get('Item')
        if pointer and pointer.get('mapped_pk') == person and pointer.get('identity_issuer') == DISCORD_ISSUER and pointer.get('identity_provider') == 'discord' and pointer.get('identity_sub') == subject:
            linked.add(subject)
    return linked


def link_discord_subjects(table, identity_key, person, subjects):
    subjects = sorted(set(subjects or []))
    if not subjects:
        return
    if not isinstance(person, str) or not person or len(subjects) > 99:
        raise ValueError('Invalid Discord aliases')
    if any(not isinstance(subject, str) or not re.fullmatch(r'\d{1,32}', subject) for subject in subjects):
        raise ValueError('Invalid Discord subject')
    pending = [subject for subject in subjects if subject not in _linked_subjects(table, identity_key, person, subjects)]
    if not pending:
        return
    writes = [{'ConditionCheck': {'TableName': table.name, 'Key': {'pk': person}, 'ConditionExpression': 'attribute_exists(pk)'}}]
    for subject in pending:
        writes.append({'Put': {'TableName': table.name,
            'Item': {'pk': identity_key(DISCORD_ISSUER, subject), 'mapped_pk': person, 'identity_issuer': DISCORD_ISSUER,
                     'identity_provider': 'discord', 'identity_sub': subject},
            'ConditionExpression': 'attribute_not_exists(pk) OR (mapped_pk = :person AND identity_issuer = :issuer AND identity_provider = :provider AND identity_sub = :subject)',
            'ExpressionAttributeValues': {':person': person, ':issuer': DISCORD_ISSUER, ':provider': 'discord', ':subject': subject}}})
    try:
        table.meta.client.transact_write_items(TransactItems=writes)
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'TransactionCanceledException' or _linked_subjects(table, identity_key, person, pending) != set(pending):
            raise
