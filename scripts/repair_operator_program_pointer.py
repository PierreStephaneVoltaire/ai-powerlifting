import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import boto3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--table', default=os.getenv('IF_HEALTH_TABLE_NAME', 'if-health'))
    parser.add_argument('--sessions-table', default=os.getenv('IF_SESSIONS_TABLE_NAME', 'if-sessions'))
    args = parser.parse_args()
    table = boto3.client('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1'))
    pointer_key = {'pk': {'S': 'operator'}, 'sk': {'S': 'program#current'}}
    pointer = table.get_item(TableName=args.table, Key=pointer_key, ConsistentRead=True).get('Item') or {}
    v020 = table.get_item(TableName=args.table, Key={'pk': {'S': 'operator'}, 'sk': {'S': 'program#v020'}}, ConsistentRead=True).get('Item') or {}
    v021 = table.get_item(TableName=args.table, Key={'pk': {'S': 'operator'}, 'sk': {'S': 'program#v021'}}, ConsistentRead=True).get('Item') or {}
    sessions = boto3.client('dynamodb', region_name=os.getenv('AWS_REGION', 'ca-central-1'))
    counts = {'program#v020': 0, 'program#v021': 0}
    last_key = None
    while True:
        query = {'TableName': args.sessions_table, 'KeyConditionExpression': '#pk = :pk AND begins_with(#sk, :prefix)', 'ExpressionAttributeNames': {'#pk': 'pk', '#sk': 'sk'}, 'ExpressionAttributeValues': {':pk': {'S': 'operator'}, ':prefix': {'S': 'session#program#'}}}
        if last_key: query['ExclusiveStartKey'] = last_key
        response = sessions.query(**query)
        for item in response.get('Items', []):
            key = item.get('sk', {}).get('S', '')
            for version in counts:
                if key.startswith(f'session#{version}#'): counts[version] += 1
        last_key = response.get('LastEvaluatedKey')
        if not last_key: break
    snapshot = json.load(open('/tmp/operator-training-programs-20260915.json'))
    expected_pointer = snapshot['pointer']
    assert pointer.get('ref_sk') == expected_pointer['ref_sk']
    assert pointer.get('updated_at') == expected_pointer['updated_at']
    assert pointer.get('version') == expected_pointer['version']
    assert digest(v020) == digest(snapshot['v020'])
    assert digest(v021) == digest(snapshot['v021'])
    assert counts == {'program#v020': 453, 'program#v021': 0}
    print(json.dumps({'mode': 'apply' if args.apply else 'dry-run', 'current': pointer.get('ref_sk'), 'replacement': 'program#v020', 'v020_hash': digest(v020), 'v021_hash': digest(v021), 'session_counts': counts, 'delta': {'ref_sk': 'program#v021 -> program#v020'}}, indent=2))
    if not args.apply:
        return
    now = datetime.now(timezone.utc).isoformat()
    result = table.update_item(TableName=args.table, Key=pointer_key, UpdateExpression='SET ref_sk = :ref, updated_at = :now, revision = :revision', ConditionExpression='ref_sk = :old AND updated_at = :timestamp AND version = :version AND attribute_not_exists(revision)', ExpressionAttributeValues={':ref': {'S': 'program#v020'}, ':now': {'S': now}, ':revision': {'N': '1'}, ':old': {'S': 'program#v021'}, ':timestamp': expected_pointer['updated_at'], ':version': {'N': '21'}}, ReturnValues='ALL_NEW')
    confirmed = result['Attributes']
    print(json.dumps({'post_update': {key: confirmed[key] for key in ('ref_sk', 'version', 'revision')}}, indent=2))


if __name__ == '__main__':
    main()
