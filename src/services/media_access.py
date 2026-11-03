import os

from .access_store import database
from .dispatch import OperationError


def additional_permission(operation: str, arguments: dict, athlete: str) -> str | None:
    if operation == 'video_upload_presign':
        return 'lift-profiles:write' if arguments.get('lift') else None
    if operation not in {'video_upload_confirm', 'video_media_resolve', 'video_remove', 'video_update_metadata'}:
        return None
    identifiers = [str(arguments.get('video_id') or '')]
    if operation == 'video_media_resolve':
        parts = str(arguments.get('s3_key') or '').split('/')
        identifiers = [parts[-1].rsplit('.', 1)[0], parts[-2] if len(parts) > 1 else '']
    table = database().Table(os.getenv('IF_HEALTH_TABLE_NAME', 'if-health'))
    for identifier in filter(None, identifiers):
        media = table.get_item(Key={'pk': athlete, 'sk': f'Media#{identifier}'}, ConsistentRead=True).get('Item')
        if media and str(media.get('media_id') or media.get('video_id') or '') == identifier:
            if media.get('lift'):
                return 'lift-profiles:read' if operation == 'video_media_resolve' else 'lift-profiles:write'
            return None
    raise OperationError(403, 'forbidden', 'Media allocation is unavailable for this Athlete')
