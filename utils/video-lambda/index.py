import json
import os
import subprocess
import tempfile
import urllib.parse
import boto3
from boto3.dynamodb.conditions import Key, Attr
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

            # Generate thumbnail
            thumbnail_key = f"thumbnails/{session_date}/{video_id}.jpg"
            thumbnail_data = generate_thumbnail(bucket, key)

            # Upload thumbnail to S3
            s3.put_object(
                Bucket=bucket,
                Key=thumbnail_key,
                Body=thumbnail_data,
                ContentType='image/jpeg'
            )

            thumbnail_url = f"https://{bucket}.s3.{os.environ.get('AWS_REGION', 'us-east-1')}.amazonaws.com/{thumbnail_key}"

            # Update DynamoDB
            update_video_thumbnail(pk, sk, session_date, video_id, thumbnail_url, thumbnail_key, 'ready')

            print(f"Successfully generated thumbnail for video {video_id}")

        except Exception as e:
            print(f"Thumbnail generation failed: {e}")

            # Try to mark as failed if we have the metadata
            try:
                response = s3.head_object(Bucket=bucket, Key=key)
                metadata = response.get('Metadata', {})

                if metadata.get('video_id') and metadata.get('session_date') and metadata.get('sk'):
                    update_video_thumbnail(
                        metadata.get('pk'),
                        metadata.get('sk'),
                        metadata.get('session_date'),
                        metadata.get('video_id'),
                        '', '', 'failed'
                    )
            except Exception as update_err:
                print(f"Failed to mark video as failed: {update_err}")


def generate_thumbnail(bucket: str, key: str) -> bytes:
    """Download video and extract thumbnail frame using ffmpeg."""
    ext = key.split('.')[-1] if '.' in key else 'mp4'
    ffmpeg_path = '/opt/bin/ffmpeg'

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, f'input.{ext}')
        thumbnail_path = os.path.join(tmpdir, 'thumbnail.jpg')

        # Download video
        s3.download_file(bucket, key, video_path)

        # Extract frame at 2 seconds using ffmpeg
        cmd = [
            ffmpeg_path if os.path.exists(ffmpeg_path) else 'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:02',
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-q:v', '5',
            '-y', thumbnail_path
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            # Try extracting from the beginning if 2 seconds fails
            cmd[4] = '00:00:00'
            subprocess.run(cmd, capture_output=True, check=True)

        with open(thumbnail_path, 'rb') as f:
            return f.read()


def update_video_thumbnail(
    pk: str,
    program_sk: str,
    session_date: str,
    video_id: str,
    thumbnail_url: str,
    thumbnail_s3_key: str,
    status: str
):
    """Update video thumbnail metadata in DynamoDB (if-sessions table)."""
    table = dynamodb.Table(SESSIONS_TABLE_NAME)

    try:
        # 1. Find the session item in if-sessions
        # SK format: session#{program_sk}#{date}#...
        prefix = f"session#{program_sk}#{session_date}#"
        
        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(prefix)
        )
        items = response.get('Items', [])
        
        if not items:
            print(f"Session item not found: pk={pk}, prefix={prefix}")
            return

        # Usually there's only one session per date/program, but we check all just in case
        for item in items:
            videos = item.get('videos', [])
            updated = False
            for video in videos:
                if video.get('video_id') == video_id:
                    video['thumbnail_url'] = thumbnail_url
                    video['thumbnail_s3_key'] = thumbnail_s3_key
                    video['thumbnail_status'] = status
                    updated = True
                    break
            
            if updated:
                # 2. Update the session item
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


from datetime import datetime
