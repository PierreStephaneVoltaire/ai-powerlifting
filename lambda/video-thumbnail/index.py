import copy
import os
import re
import subprocess
import tempfile
import urllib.parse
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('TABLE_NAME', 'if-health')
SESSIONS_TABLE_NAME = os.environ.get('SESSIONS_TABLE_NAME', 'if-sessions')
VIDEOS_BUCKET = os.environ.get('VIDEOS_BUCKET', 'powerlifting-session-videos')
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MAX_FORM_VIDEO_SECONDS = 180


def _table():
    return dynamodb.Table(TABLE_NAME)


def _notifications_module():
    import notifications
    return notifications


def _notify_media_ready(media):
    notification = _notifications_module().media_ready_notification(media)
    if notification is None:
        return False
    person, event_id, kind, payload = notification
    table = dynamodb.Table(_notifications_module().notification_table_name())
    try:
        table.meta.client.transact_write_items(
            TransactItems=_notifications_module().notification_transaction_items(person, event_id, kind, payload)
        )
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') != 'TransactionCanceledException':
            raise
        if table.get_item(Key=_notifications_module().notification_marker_key(event_id), ConsistentRead=True).get('Item'):
            return False
        raise
    return True


def _media(table, pk, video_id):
    item = table.get_item(Key={'pk': pk, 'sk': f'Media#{video_id}'}, ConsistentRead=True).get('Item')
    if not item or str(item.get('media_id') or item.get('video_id') or '') != video_id:
        raise ValueError('Media allocation not found')
    return item


def _decimals(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimals(item) for item in value]
    return value


def _update_lift_profile_video(media, status, processed_key='', thumbnail_key='', failure=''):
    lift = str(media.get('lift') or '')
    angle = str(media.get('angle') or '')
    if lift not in {'squat', 'bench', 'deadlift'} or angle not in {'front', 'side', 'diagonal'}:
        return
    table = _table()
    for _ in range(5):
        pointer = table.get_item(Key={'pk': media['pk'], 'sk': 'program#current'}, ConsistentRead=True).get('Item') or {}
        program_keys = [str(media['program_sk'])]
        if pointer.get('ref_sk') and str(pointer['ref_sk']) not in program_keys:
            program_keys.append(str(pointer['ref_sk']))
        program = None
        slot = None
        profile = None
        profiles = []
        for program_key in program_keys:
            candidate = table.get_item(Key={'pk': media['pk'], 'sk': program_key}, ConsistentRead=True).get('Item')
            candidate_profiles = copy.deepcopy((candidate or {}).get('lift_profiles') or [])
            candidate_profile = next((item for item in candidate_profiles if item.get('lift') == lift), None)
            candidate_slot = (candidate_profile or {}).get('form_videos', {}).get(angle)
            if isinstance(candidate_slot, dict) and str(candidate_slot.get('pending_media_id') or '') == str(media.get('video_id')) and str(candidate_slot.get('target_revision') or '') == str(media.get('target_revision') or ''):
                program, profiles, slot, profile = candidate, candidate_profiles, candidate_slot, candidate_profile
                break
        if not program or not profile or not isinstance(slot, dict):
            return False
        if status == 'ready':
            replacement = {
                **slot,
                'video_id': media['video_id'],
                's3_key': processed_key,
                'thumbnail_s3_key': thumbnail_key,
                'video_url': f'/api/videos/media/{processed_key}',
                'thumbnail_url': f'/api/videos/media/{thumbnail_key}',
                'thumbnail_status': 'ready',
                'processing_status': 'ready',
                'allocation_revision': int(media.get('allocation_revision', 0)),
            }
            replacement.pop('pending_media_id', None)
            replacement.pop('pending_s3_key', None)
        else:
            replacement = {**slot, 'processing_status': 'failed', 'failure': str(failure)}
        profile['form_videos'] = {**profile.get('form_videos', {}), angle: replacement}
        revision = (program.get('meta') or {}).get('revision')
        if revision is None:
            table.update_item(
                Key={'pk': program['pk'], 'sk': program['sk']},
                UpdateExpression='SET lift_profiles = :profiles',
                ExpressionAttributeValues={':profiles': _decimals(profiles)},
            )
            return True
        try:
            table.update_item(
                Key={'pk': program['pk'], 'sk': program['sk']},
                UpdateExpression='SET lift_profiles = :profiles',
                ConditionExpression='#meta.#revision = :revision',
                ExpressionAttributeNames={'#meta': 'meta', '#revision': 'revision'},
                ExpressionAttributeValues={':profiles': _decimals(profiles), ':revision': revision},
            )
            return True
        except ClientError as error:
            if error.response.get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
                raise
    return False


def _put_media(table, item, expected_statuses, expected_status=None):
    status = expected_status if expected_status is not None else item.get('status')
    if status not in expected_statuses:
        return item
    table.put_item(
        Item=item,
        ConditionExpression='allocation_revision = :revision AND #status = :status',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={':revision': item['allocation_revision'], ':status': status},
    )
    return item


def _form_duration_seconds(ffmpeg_path, input_path):
    ffprobe_path = '/opt/bin/ffprobe' if os.path.exists('/opt/bin/ffprobe') else None
    if ffprobe_path:
        probe = subprocess.run([
            ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path,
        ], capture_output=True, text=True, check=True)
        return float(probe.stdout.strip() or 0)
    probe = subprocess.run([ffmpeg_path, '-i', input_path, '-f', 'null', '-'], capture_output=True, text=True, check=False)
    match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', getattr(probe, 'stderr', ''))
    if not match:
        raise ValueError('Unable to determine form video duration')
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _complete_media(pk, video_id, revision, source_size, processed_key, thumbnail_key):
    table = _table()
    current = _media(table, pk, video_id)
    if int(current.get('allocation_revision', 0)) != revision:
        return current
    if current.get('status') not in {'allocated', 'processing', 'confirmed', 'ready'}:
        return current
    if current.get('status') == 'ready':
        return current
    updated = {
        **current,
        'status': 'confirmed' if current.get('status') == 'confirmed' else 'ready',
        'source_size': source_size,
        'processed_s3_key': processed_key,
        'thumbnail_s3_key': thumbnail_key,
        'video_url': f'/api/videos/media/{processed_key}',
        'thumbnail_url': f'/api/videos/media/{thumbnail_key}',
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        return _put_media(table, updated, (current.get('status'),), current.get('status'))
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return _media(table, pk, video_id)
        raise


def _mark_failed(pk, video_id, revision, message):
    table = _table()
    try:
        current = _media(table, pk, video_id)
    except ValueError:
        return False
    if int(current.get('allocation_revision', 0)) != revision or current.get('status') == 'ready' or (
        current.get('status') == 'confirmed' and current.get('processed_s3_key')
    ):
        return False
    updated = {**current, 'status': 'failed', 'failure': str(message), 'updated_at': datetime.now(timezone.utc).isoformat()}
    try:
        _put_media(table, updated, (current.get('status'),), current.get('status'))
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
            raise
        return False
    return True


def _mark_processing(media):
    if media.get('status') != 'allocated':
        return media
    table = _table()
    updated = {**media, 'status': 'processing', 'updated_at': datetime.now(timezone.utc).isoformat()}
    try:
        return _put_media(table, updated, ('allocated',), 'allocated')
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return _media(table, media['pk'], media['video_id'])
        raise


def _process_record(bucket, key):
    source = s3.head_object(Bucket=bucket, Key=key)
    metadata = {str(k).lower(): str(v) for k, v in (source.get('Metadata') or {}).items()}
    video_id = metadata.get('video_id') or metadata.get('media_id')
    required = ('session_date', 'session_id', 'pk', 'sk', 'allocation_revision')
    if not video_id or any(not metadata.get(field) for field in required):
        raise ValueError(f'Missing media allocation metadata for {key}')
    if metadata.get('media_id') and metadata.get('media_id') != video_id:
        raise ValueError('Stale media allocation')
    source_size = int(source.get('ContentLength') or 0)
    if source_size <= 0 or source_size > MAX_VIDEO_BYTES:
        raise ValueError('Uploaded video size is invalid')
    media = _media(_table(), metadata['pk'], video_id)
    revision = int(metadata['allocation_revision'])
    for field, value in (('video_id', video_id), ('session_id', metadata['session_id']), ('session_date', metadata['session_date']), ('pk', metadata['pk']), ('program_sk', metadata['sk'])):
        if str(media.get(field) or '') != value:
            raise ValueError('Media allocation metadata does not match registry')
    for field in ('lift', 'angle', 'target_revision'):
        if media.get(field) is not None and metadata.get(field) != str(media[field]):
            raise ValueError('Media allocation metadata does not match registry')
    if str(media.get('source_s3_key') or media.get('s3_key')) != key or int(media.get('allocation_revision', 0)) != revision:
        raise ValueError('Stale media allocation')
    if media.get('status') == 'legacy':
        return media
    if media.get('expected_size') is not None and metadata.get('expected_size') != str(media['expected_size']):
        raise ValueError('Uploaded video metadata does not match allocation')
    if media.get('status') == 'removed':
        raise ValueError('Media allocation was removed')
    if media.get('status') in {'ready', 'confirmed'} and media.get('processed_s3_key') and media.get('thumbnail_s3_key'):
        slot_updated = _update_lift_profile_video(media, 'ready', media['processed_s3_key'], media['thumbnail_s3_key'])
        if media.get('lift') and media.get('angle') and not slot_updated:
            return media
        update_video_metadata(
            metadata['pk'], metadata['sk'], metadata['session_date'], video_id,
            f"/api/videos/media/{media['processed_s3_key']}", media['processed_s3_key'],
            f"/api/videos/media/{media['thumbnail_s3_key']}", media['thumbnail_s3_key'], 'ready',
            session_id=metadata['session_id'],
            allocation_revision=revision,
        )
        _notify_media_ready(media)
        return media
    expected_size = media.get('expected_size') or metadata.get('expected_size')
    if expected_size is not None and source_size != int(expected_size):
        raise ValueError('Uploaded video size does not match allocation')
    processing = _mark_processing(media)
    if processing.get('status') not in {'processing', 'confirmed'}:
        raise ValueError('Media allocation is no longer active')
    target_video_key = f"processed/{metadata['session_date']}/{video_id}/r{revision}.mp4"
    thumbnail_key = f"thumbnails/{metadata['session_date']}/{video_id}/r{revision}.jpg"
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, 'input')
        output_path = os.path.join(tmpdir, 'output.mp4')
        thumbnail_path = os.path.join(tmpdir, 'thumbnail.jpg')
        s3.download_file(bucket, key, input_path)
        ffmpeg_path = '/opt/bin/ffmpeg' if os.path.exists('/opt/bin/ffmpeg') else 'ffmpeg'
        if media.get('lift'):
            if _form_duration_seconds(ffmpeg_path, input_path) > MAX_FORM_VIDEO_SECONDS:
                raise ValueError('Form video exceeds the three-minute limit')
        subprocess.run([
            ffmpeg_path, '-i', input_path, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-y', output_path,
        ], capture_output=True, check=True)
        subprocess.run([
            ffmpeg_path, '-i', output_path, '-ss', '00:00:01', '-vframes', '1',
            '-vf', 'scale=320:-1', '-q:v', '5', '-y', thumbnail_path,
        ], capture_output=True, check=True)
        with open(output_path, 'rb') as output:
            s3.put_object(Bucket=bucket, Key=target_video_key, Body=output, ContentType='video/mp4')
        with open(thumbnail_path, 'rb') as thumbnail:
            s3.put_object(Bucket=bucket, Key=thumbnail_key, Body=thumbnail, ContentType='image/jpeg')
    completed = _complete_media(metadata['pk'], video_id, revision, source_size, target_video_key, thumbnail_key)
    if (
        not completed
        or int(completed.get('allocation_revision', 0)) != revision
        or completed.get('processed_s3_key') != target_video_key
        or completed.get('thumbnail_s3_key') != thumbnail_key
        or completed.get('status') not in {'ready', 'confirmed'}
    ):
        return completed
    slot_updated = _update_lift_profile_video(completed, 'ready', target_video_key, thumbnail_key)
    if completed.get('lift') and completed.get('angle') and not slot_updated:
        return completed
    update_video_metadata(
        metadata['pk'], metadata['sk'], metadata['session_date'], video_id,
        f'/api/videos/media/{target_video_key}', target_video_key,
        f'/api/videos/media/{thumbnail_key}', thumbnail_key, 'ready', session_id=metadata['session_id'],
        allocation_revision=revision,
    )
    _notify_media_ready(completed)
    return completed


def handler(event, context):
    for record in event.get('Records', []):
        s3_info = record.get('s3', {})
        bucket = s3_info.get('bucket', {}).get('name') or VIDEOS_BUCKET
        key = urllib.parse.unquote_plus(s3_info.get('object', {}).get('key', ''))
        if not key:
            raise ValueError('Invalid S3 event record')
        try:
            _process_record(bucket, key)
        except Exception as error:
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                metadata = {str(k).lower(): str(v) for k, v in (head.get('Metadata') or {}).items()}
                if metadata.get('pk') and metadata.get('video_id') and metadata.get('allocation_revision') and _mark_failed(metadata['pk'], metadata['video_id'], int(metadata['allocation_revision']), error):
                    _update_lift_profile_video(_media(_table(), metadata['pk'], metadata['video_id']), 'failed', failure=error)
                    update_video_metadata(
                        metadata['pk'], metadata.get('sk', ''), metadata.get('session_date', ''), metadata['video_id'],
                        '', '', '', '', 'failed', session_id=metadata.get('session_id', ''),
                        allocation_revision=int(metadata['allocation_revision']),
                    )
            finally:
                raise


def update_video_metadata(pk, program_sk, session_date, video_id, video_url, video_s3_key, thumbnail_url, thumbnail_s3_key, status, _attempt=0, session_id=None, allocation_revision=None):
    media = _media(_table(), pk, video_id)
    if allocation_revision is not None and (
        int(media.get('allocation_revision', 0)) != int(allocation_revision)
        or media.get('status') not in {'ready', 'confirmed', 'failed'}
        or (status == 'ready' and media.get('processed_s3_key') != video_s3_key)
    ):
        return
    table = dynamodb.Table(SESSIONS_TABLE_NAME)
    prefix = f'session#{program_sk}#{session_date}#'
    items = table.query(KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(prefix)).get('Items', [])
    item = next((candidate for candidate in items if session_id is None or str(candidate.get('session_id') or candidate.get('id') or '') == str(session_id)), None)
    if item is None:
        return
    videos = copy.deepcopy(item.get('videos') or [])
    for video in videos:
        if video.get('video_id') != video_id:
            continue
        if allocation_revision is not None and int(video.get('allocation_revision', 0)) != int(allocation_revision):
            return
        if status == 'failed' and video.get('thumbnail_status') == 'ready':
            return
        if video_s3_key:
            video['s3_key'] = video_s3_key
        if video_url:
            video['video_url'] = video_url
        if thumbnail_s3_key:
            video['thumbnail_s3_key'] = thumbnail_s3_key
        if thumbnail_url:
            video['thumbnail_url'] = thumbnail_url
        video['thumbnail_status'] = status
        break
    else:
        return
    revision = int(item.get('media_revision', 0))
    try:
        table.update_item(
            Key={'pk': item['pk'], 'sk': item['sk']},
            UpdateExpression='SET videos = :videos, updated_at = :updated_at, media_revision = :next',
            ConditionExpression='attribute_not_exists(media_revision) OR media_revision = :revision',
            ExpressionAttributeValues={
                ':videos': videos,
                ':updated_at': datetime.now(timezone.utc).isoformat(),
                ':next': revision + 1,
                ':revision': revision,
            },
        )
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException' and _attempt < 4:
            return update_video_metadata(pk, program_sk, session_date, video_id, video_url, video_s3_key, thumbnail_url, thumbnail_s3_key, status, _attempt + 1, session_id, allocation_revision)
        raise
