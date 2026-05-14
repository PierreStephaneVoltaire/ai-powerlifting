import json
import os
import subprocess
import tempfile
import urllib.parse
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('TABLE_NAME', 'if-health')
SESSIONS_TABLE_NAME = os.environ.get('SESSIONS_TABLE_NAME', 'if-sessions')
VIDEOS_BUCKET = os.environ.get('VIDEOS_BUCKET', 'powerlifting-session-videos')


def handler(event, context):
    """S3 event handler for video thumbnail generation."""
    for record in event.get('Records', []):
        s3_info = record.get('s3', {})
        bucket = s3_info.get('bucket', {}).get('name')
        key = urllib.parse.unquote_plus(s3_info.get('object', {}).get('key', ''))

        if not bucket or not key:
            print(f"Invalid record: {record}")
            continue

        print(f"Processing video: {key}")

        try:
            # Get video metadata
            response = s3.head_object(Bucket=bucket, Key=key)
            metadata = response.get('Metadata', {})

            video_id = metadata.get('video_id')
            session_date = metadata.get('session_date')
            pk = metadata.get('pk')
            sk = metadata.get('sk')

            if not all([video_id, session_date, pk, sk]):
                print(f"Missing required metadata: video_id={video_id}, session_date={session_date}, pk={pk}, sk={sk}")
                continue

            target_video_key = f"processed/{session_date}/{video_id}.mp4"
            thumbnail_key = f"thumbnails/{session_date}/{video_id}.jpg"

            with tempfile.TemporaryDirectory() as tmpdir:
                input_path = os.path.join(tmpdir, "input")
                output_path = os.path.join(tmpdir, "output.mp4")
                thumbnail_path = os.path.join(tmpdir, "thumbnail.jpg")

                print(f"Downloading input: {key}")
                s3.download_file(bucket, key, input_path)

                ffmpeg_path = '/opt/bin/ffmpeg' if os.path.exists('/opt/bin/ffmpeg') else 'ffmpeg'

                # Transcode to H.264/AAC MP4 with FastStart for web streaming
                print(f"Transcoding to: {target_video_key}")
                transcode_cmd = [
                    ffmpeg_path,
                    '-i', input_path,
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                    '-y', output_path
                ]
                subprocess.run(transcode_cmd, capture_output=True, check=True)

                # Generate thumbnail at 1 second
                print("Generating thumbnail...")
                thumb_cmd = [
                    ffmpeg_path,
                    '-i', output_path,
                    '-ss', '00:00:01',
                    '-vframes', '1',
                    '-vf', 'scale=320:-1',
                    '-q:v', '5',
                    '-y', thumbnail_path
                ]
                subprocess.run(thumb_cmd, capture_output=True, check=True)

                # Upload processed video
                with open(output_path, 'rb') as f:
                    s3.put_object(
                        Bucket=bucket,
                        Key=target_video_key,
                        Body=f.read(),
                        ContentType='video/mp4'
                    )

                # Upload thumbnail
                with open(thumbnail_path, 'rb') as f:
                    s3.put_object(
                        Bucket=bucket,
                        Key=thumbnail_key,
                        Body=f.read(),
                        ContentType='image/jpeg'
                    )

            # Proxy URLs relative to the backend — s3_key is updated to the processed path
            # so the backend's transformVideo always serves the correct file via the proxy.
            video_url = f"/api/videos/media/{target_video_key}"
            thumbnail_url = f"/api/videos/media/{thumbnail_key}"

            update_video_metadata(
                pk, sk, session_date, video_id,
                video_url, target_video_key,
                thumbnail_url, thumbnail_key,
                'ready'
            )

            print(f"Successfully processed video {video_id}")

            # Delete the original raw upload to save storage
            print(f"Cleaning up original: {key}")
            s3.delete_object(Bucket=bucket, Key=key)

        except Exception as e:
            print(f"Processing failed for {key}: {e}")
            import traceback
            traceback.print_exc()

            # Mark as failed in DynamoDB if we have enough metadata
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                meta = head.get('Metadata', {})
                if meta.get('video_id') and meta.get('session_date') and meta.get('sk'):
                    update_video_metadata(
                        meta.get('pk'),
                        meta.get('sk'),
                        meta.get('session_date'),
                        meta.get('video_id'),
                        '', '', '', '', 'failed'
                    )
            except Exception as update_err:
                print(f"Failed to mark video as failed: {update_err}")


def update_video_metadata(
    pk: str,
    program_sk: str,
    session_date: str,
    video_id: str,
    video_url: str,
    video_s3_key: str,
    thumbnail_url: str,
    thumbnail_s3_key: str,
    status: str
):
    """Update video metadata in DynamoDB (if-sessions table).

    Crucially updates s3_key to the processed path so the backend's
    transformVideo function generates the correct proxy URL.
    """
    table = dynamodb.Table(SESSIONS_TABLE_NAME)

    try:
        prefix = f"session#{program_sk}#{session_date}#"

        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(prefix)
        )
        items = response.get('Items', [])

        if not items:
            print(f"Session item not found: pk={pk}, prefix={prefix}")
            return

        for item in items:
            videos = item.get('videos', [])
            updated = False
            for video in videos:
                if video.get('video_id') == video_id:
                    video['video_url'] = video_url
                    # Update s3_key to point at the processed MP4 so the backend
                    # proxy URL is generated from the correct S3 object.
                    if video_s3_key:
                        video['s3_key'] = video_s3_key
                    video['thumbnail_url'] = thumbnail_url
                    video['thumbnail_s3_key'] = thumbnail_s3_key
                    video['thumbnail_status'] = status
                    updated = True
                    break

            if updated:
                table.update_item(
                    Key={'pk': pk, 'sk': item['sk']},
                    UpdateExpression='SET videos = :videos, updated_at = :updated_at',
                    ExpressionAttributeValues={
                        ':videos': videos,
                        ':updated_at': datetime.utcnow().isoformat()
                    }
                )
                print(f"Updated session item {item['sk']}")
                break

    except ClientError as e:
        print(f"DynamoDB update failed: {e}")
        raise
