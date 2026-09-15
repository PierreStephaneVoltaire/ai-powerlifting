import argparse
import os

import boto3
from boto3.dynamodb.conditions import Key


def register_existing_media(health_table, sessions_table, pk, program_sk=None):
    kwargs = {'KeyConditionExpression': Key('pk').eq(pk) & Key('sk').begins_with('session#')}
    registered = 0
    while True:
        response = sessions_table.query(**kwargs)
        for session in response.get('Items', []):
            if program_sk and session.get('program_sk') != program_sk:
                continue
            session_id = str(session.get('session_id') or session.get('id') or str(session.get('sk', '')).rsplit('#', 1)[-1])
            date = str(session.get('date') or '')
            raw_sk = str(session.get('sk') or '')
            parts = raw_sk.split('#')
            version = str(session.get('program_sk') or ('#'.join(parts[1:3]) if len(parts) >= 3 else ''))
            for video in session.get('videos') or []:
                video_id = str(video.get('video_id') or '')
                source_key = str(video.get('s3_key') or '')
                if not video_id or not date or not source_key:
                    continue
                item = {
                    'pk': pk,
                    'sk': f'Media#{video_id}',
                    'entity_type': 'media',
                    'media_id': video_id,
                    'video_id': video_id,
                    'session_id': session_id,
                    'session_date': date,
                    'program_sk': version,
                    's3_key': source_key,
                    'source_s3_key': source_key,
                    'allocation_revision': 0,
                    'status': 'legacy',
                    'legacy': True,
                    'readonly': True,
                    'ownership_source': 'trusted-session-record',
                }
                if source_key.startswith('processed/'):
                    item['processed_s3_key'] = source_key
                if video.get('thumbnail_s3_key'):
                    item['thumbnail_s3_key'] = video['thumbnail_s3_key']
                try:
                    health_table.put_item(Item=item, ConditionExpression='attribute_not_exists(pk)')
                    registered += 1
                except Exception as error:
                    if getattr(error, 'response', {}).get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
                        raise
        if not response.get('LastEvaluatedKey'):
            break
        kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
    return registered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pk', default=os.environ.get('HEALTH_PROGRAM_PK', 'operator'))
    parser.add_argument('--program-sk')
    args = parser.parse_args()
    region = os.environ.get('AWS_REGION', 'ca-central-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    count = register_existing_media(
        dynamodb.Table(os.environ.get('IF_HEALTH_TABLE_NAME', 'if-health')),
        dynamodb.Table(os.environ.get('IF_SESSIONS_TABLE_NAME', 'if-sessions')),
        args.pk,
        args.program_sk,
    )
    print(f'registered {count} media records for {args.pk}')


if __name__ == '__main__':
    main()
